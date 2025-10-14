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
    async def stream_run(run_id: int):
        """Simple Server-Sent Events (SSE) endpoint for run logs.
        This keeps the connection open and emits periodic keepalive comments so
        EventSource clients do not see a 404. It validates the run exists in the
        in-memory store or database and otherwise returns 404.
        """
        # verify run exists in memory or DB
        exists = False
        try:
            if hasattr(shared, '_runs') and run_id in shared._runs:
                exists = True
            elif getattr(shared, '_DB_AVAILABLE', False):
                try:
                    db = shared.SessionLocal()
                    r = db.query(shared.models.Run).filter(shared.models.Run.id == run_id).first()
                    if r:
                        exists = True
                except Exception:
                    pass
                finally:
                    try:
                        db.close()
                    except Exception:
                        pass
        except Exception:
            # fall through to 404 below
            exists = exists
        if not exists:
            raise HTTPException(status_code=404, detail='run not found')

        async def event_stream():
            import asyncio
            # emit a periodic comment to keep connection alive. Real implementation
            # would stream actual run log events as they arrive.
            try:
                while True:
                    await asyncio.sleep(15)
                    # SSE comment/heartbeat (a line beginning with ':'), followed by a blank line.
                    yield ':\n\n'
            except asyncio.CancelledError:
                return

        return StreamingResponse(event_stream(), media_type='text/event-stream')

    @app.get('/api/runs/{run_id}')
    def get_run_detail(run_id: int, authorization: Optional[str] = Header(None)):
        return shared.get_run_detail_impl(run_id, authorization)
