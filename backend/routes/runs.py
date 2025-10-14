def register(app, ctx):
    from . import shared_impls as shared
    from fastapi import HTTPException, Header
    from typing import Optional
    from fastapi.responses import StreamingResponse

    @app.post('/api/workflows/{wf_id}/run')
    def manual_run(wf_id: int, request: dict, authorization: Optional[str] = Header(None)):
        return shared.manual_run_impl(wf_id, request, authorization)

    @app.post('/api/runs/{run_id}/retry')
    def retry_run(run_id: int, authorization: Optional[str] = Header(None)):
        return shared.retry_run_impl(run_id, authorization)

    @app.get('/api/runs')
    def list_runs(workflow_id: Optional[int] = None, limit: Optional[int] = 50, offset: Optional[int] = 0, authorization: Optional[str] = Header(None)):
        return shared.list_runs_impl(workflow_id, limit, offset, authorization)

    @app.get('/api/runs/{run_id}/logs')
    def get_run_logs(run_id: int):
        return {'logs': []}

    @app.get('/api/runs/{run_id}/stream')
    async def stream_run(run_id: int, authorization: Optional[str] = Header(None)):
        """SSE endpoint that streams RunLog rows for a run in real-time.

        Behavior:
        - Requires Authorization header (token-based) and verifies the user owns
          the workspace containing the run (DB) or is the creator for in-memory
          runs.
        - Streams existing logs on connect and then polls for new RunLog rows
          every 1s, yielding them as SSE "data: <json>\n\n" messages.
        - Emits periodic comment heartbeats when idle to keep EventSource alive.
        - Closes the connection when the run reaches a terminal state
          (success/failed) and all logs have been sent.
        """
        import asyncio
        import json
        from datetime import datetime

        # authenticate
        user_id = None
        try:
            user_id = shared._user_from_token(authorization)
        except Exception:
            user_id = None
        if not user_id:
            raise HTTPException(status_code=401, detail='authorization required')

        # Authorization / run existence checks
        db = None
        run_row = None
        in_memory = False
        try:
            if getattr(shared, '_DB_AVAILABLE', False):
                try:
                    db = shared.SessionLocal()
                    # load run and workflow to check workspace ownership
                    from backend import models as _models
                    run_row = db.query(_models.Run).filter(_models.Run.id == run_id).first()
                    if not run_row:
                        # fall back to in-memory store
                        if hasattr(shared, '_runs') and run_id in shared._runs:
                            in_memory = True
                        else:
                            raise HTTPException(status_code=404, detail='run not found')
                    else:
                        # verify workspace ownership via workflow
                        wf = db.query(_models.Workflow).filter(_models.Workflow.id == run_row.workflow_id).first()
                        wsid = None
                        if wf:
                            wsid = getattr(wf, 'workspace_id', None)
                        # fallback: try shared._workspace_for_user to find user's workspace
                        user_wsid = shared._workspace_for_user(user_id)
                        if wsid is not None and user_wsid != wsid:
                            raise HTTPException(status_code=403, detail='not allowed')
                except HTTPException:
                    raise
                except Exception:
                    # if DB queries fail for any reason, deny access conservatively
                    raise HTTPException(status_code=500, detail='internal error')
            else:
                # DB not available: check in-memory run
                if hasattr(shared, '_runs') and run_id in shared._runs:
                    r = shared._runs.get(run_id)
                    if r.get('created_by') != user_id:
                        raise HTTPException(status_code=403, detail='not allowed')
                    in_memory = True
                else:
                    raise HTTPException(status_code=404, detail='run not found')
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

        async def event_stream():
            """Poll DB for new RunLog rows and yield SSE events."""
            db = None
            last_id = 0
            last_activity = 0
            heartbeat_interval = 15
            poll_interval = 1
            try:
                if getattr(shared, '_DB_AVAILABLE', False):
                    db = shared.SessionLocal()
                # on connect, send existing logs (if DB available)
                if db is not None:
                    try:
                        from backend import models as _models
                        rows = db.query(_models.RunLog).filter(_models.RunLog.run_id == run_id).order_by(_models.RunLog.id.asc()).all()
                        out = []
                        for rr in rows:
                            last_id = max(last_id, getattr(rr, 'id', 0))
                            out.append({'id': rr.id, 'run_id': rr.run_id, 'node_id': rr.node_id, 'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None, 'level': rr.level, 'message': rr.message})
                        for item in out:
                            yield f"data: {json.dumps(item)}\n\n"
                            last_activity = asyncio.get_event_loop().time()
                    except Exception:
                        # ignore initial read errors but continue streaming
                        pass
                else:
                    # no DB: for in-memory runs there are no persisted logs; just send a note
                    yield f"data: {json.dumps({'note': 'in-memory run; no persisted logs'})}\n\n"
                    last_activity = asyncio.get_event_loop().time()

                # Poll loop
                while True:
                    # if DB available, fetch new rows since last_id
                    sent_any = False
                    if db is not None:
                        try:
                            from backend import models as _models
                            rows = db.query(_models.RunLog).filter(_models.RunLog.run_id == run_id, _models.RunLog.id > last_id).order_by(_models.RunLog.id.asc()).all()
                            for rr in rows:
                                item = {'id': rr.id, 'run_id': rr.run_id, 'node_id': rr.node_id, 'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None, 'level': rr.level, 'message': rr.message}
                                last_id = max(last_id, getattr(rr, 'id', 0))
                                yield f"data: {json.dumps(item)}\n\n"
                                sent_any = True
                                last_activity = asyncio.get_event_loop().time()
                        except Exception:
                            # swallow transient DB errors
                            pass

                        # check run terminal state and close if finished and no pending logs
                        try:
                            from backend import models as _models
                            r = db.query(_models.Run).filter(_models.Run.id == run_id).first()
                            if r and getattr(r, 'status', None) in ('success', 'failed'):
                                # if we've sent all logs, emit a final event and close
                                yield f"data: {json.dumps({'run_id': run_id, 'status': r.status})}\n\n"
                                return
                        except Exception:
                            pass

                    # if we've sent anything recently, reset heartbeat timer
                    now = asyncio.get_event_loop().time()
                    if (now - last_activity) >= heartbeat_interval:
                        # send SSE comment as heartbeat
                        yield ':\n\n'
                        last_activity = now

                    try:
                        await asyncio.sleep(poll_interval)
                    except asyncio.CancelledError:
                        return

            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass

        return StreamingResponse(event_stream(), media_type='text/event-stream')

    @app.get('/api/runs/{run_id}')
    def get_run_detail(run_id: int, authorization: Optional[str] = Header(None)):
        return shared.get_run_detail_impl(run_id, authorization)
