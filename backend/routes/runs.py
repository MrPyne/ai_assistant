def register(app, ctx):
    from . import shared_impls as shared
    try:
        from fastapi import HTTPException, Header
        from fastapi.responses import StreamingResponse
        from typing import Optional
        _FASTAPI = True
    except Exception:
        class HTTPException(Exception):
            def __init__(self, status_code: int = 500, detail: str = None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        def Header(default=None, **kwargs):
            return default

        class StreamingResponse:
            def __init__(self, gen, media_type=None):
                self._gen = gen
                self.media_type = media_type

            def __iter__(self):
                return iter(self._gen)

        from typing import Optional
        _FASTAPI = False

    @app.post('/api/workflows/{wf_id}/run')
    def manual_run(wf_id: int, request: dict, authorization: Optional[str] = Header(None)):
        try:
            from fastapi import Request
        except Exception:
            Request = None
        return shared.manual_run_impl(wf_id, request, authorization)

    @app.post('/api/runs/{run_id}/retry')
    def retry_run(run_id: int, authorization: Optional[str] = Header(None)):
        return shared.retry_run_impl(run_id, authorization)

    @app.get('/api/runs')
    def list_runs(workflow_id: Optional[int] = None, limit: Optional[int] = 50, offset: Optional[int] = 0, authorization: Optional[str] = Header(None), request: Optional["Request"] = None):
        auth = authorization
        try:
            if (not auth) and request is not None:
                auth = request.query_params.get('token') or auth
        except Exception:
            pass
        return shared.list_runs_impl(workflow_id, limit, offset, auth)

    @app.get('/api/runs/{run_id}/logs')
    def get_run_logs(run_id: int):
        import json
        try:
            if getattr(shared, '_DB_AVAILABLE', False):
                db = None
                try:
                    db = shared.SessionLocal()
                    from backend import models as _models

                    rows = (
                        db.query(_models.RunLog)
                        .filter(_models.RunLog.run_id == run_id)
                        .order_by(_models.RunLog.id.asc())
                        .all()
                    )
                    out = []
                    for rr in rows:
                        try:
                            payload = None
                            try:
                                payload = json.loads(rr.message) if rr.message else None
                            except Exception:
                                payload = None

                            if isinstance(payload, dict) and 'type' in payload:
                                payload.setdefault('run_id', rr.run_id)
                                payload.setdefault('node_id', rr.node_id)
                                payload.setdefault('timestamp', rr.timestamp.isoformat() if rr.timestamp is not None else None)
                                try:
                                    payload.setdefault('event_id', getattr(rr, 'event_id', None))
                                except Exception:
                                    pass
                                out.append(payload)
                            else:
                                out.append({
                                    'type': 'log',
                                    'id': rr.id,
                                    'run_id': rr.run_id,
                                    'node_id': rr.node_id,
                                    'event_id': getattr(rr, 'event_id', None),
                                    'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None,
                                    'level': rr.level,
                                    'message': rr.message,
                                })
                        except Exception:
                            continue
                    return {'logs': out}
                finally:
                    try:
                        if db is not None:
                            db.close()
                    except Exception:
                        pass

            if hasattr(shared, '_runs') and run_id in shared._runs:
                r = shared._runs.get(run_id)
                return {'logs': r.get('logs', [])}
            return {'logs': []}
        except Exception:
            return {'logs': []}

    @app.get('/api/runs/{run_id}/stream')
    async def stream_run(run_id: int, authorization: Optional[str] = Header(None), request: Optional["Request"] = None):
        """SSE endpoint that delegates the streaming implementation to
        backend.routes.runs_stream.event_stream_generator to keep this
        module small and focused on route registration.
        """
        import logging

        logger = logging.getLogger(__name__)

        user_id = None
        try:
            auth = authorization
            try:
                if (not auth) and request is not None:
                    auth = request.query_params.get('token') or auth
            except Exception:
                pass
            user_id = shared._user_from_token(auth)
        except Exception:
            user_id = None
        if not user_id:
            raise HTTPException(status_code=401, detail='authorization required')
        logger.info("SSE connect requested run_id=%s user_id=%s", run_id, user_id)

        # perform pre-checks (existence/permission) similar to original
        db = None
        try:
            if getattr(shared, '_DB_AVAILABLE', False):
                try:
                    db = shared.SessionLocal()
                    from backend import models as _models
                    run_row = db.query(_models.Run).filter(_models.Run.id == run_id).first()
                    if not run_row:
                        if hasattr(shared, '_runs') and run_id in shared._runs:
                            pass
                        else:
                            raise HTTPException(status_code=404, detail='run not found')
                    else:
                        wf = db.query(_models.Workflow).filter(_models.Workflow.id == run_row.workflow_id).first()
                        wsid = None
                        if wf:
                            wsid = getattr(wf, 'workspace_id', None)
                        user_wsid = shared._workspace_for_user(user_id)
                        if wsid is not None and user_wsid != wsid:
                            raise HTTPException(status_code=403, detail='not allowed')
                except HTTPException:
                    raise
                except Exception:
                    raise HTTPException(status_code=500, detail='internal error')
            else:
                if hasattr(shared, '_runs') and run_id in shared._runs:
                    r = shared._runs.get(run_id)
                    if r.get('created_by') != user_id:
                        raise HTTPException(status_code=403, detail='not allowed')
                else:
                    raise HTTPException(status_code=404, detail='run not found')
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

        # Delegate heavy-lifting to extracted generator
        from backend.routes.runs_stream import event_stream_generator

        return StreamingResponse(event_stream_generator(shared, run_id), media_type='text/event-stream')

    @app.get('/api/runs/{run_id}')
    def get_run_detail(run_id: int, authorization: Optional[str] = Header(None)):
        return shared.get_run_detail_impl(run_id, authorization)
