def register(app, ctx):
    from . import _shared as shared
    from fastapi import HTTPException
    from typing import Optional

    @app.post('/api/workflows/{wf_id}/run')
    def manual_run(wf_id: int, request: dict, authorization: Optional[str] = None):
        return shared.manual_run_impl(wf_id, request, authorization)

    @app.post('/api/runs/{run_id}/retry')
    def retry_run(run_id: int, authorization: Optional[str] = None):
        return shared.retry_run_impl(run_id, authorization)

    @app.get('/api/runs')
    def list_runs(workflow_id: Optional[int] = None, limit: Optional[int] = 50, offset: Optional[int] = 0, authorization: Optional[str] = None):
        return shared.list_runs_impl(workflow_id, limit, offset, authorization)

    @app.get('/api/runs/{run_id}/logs')
    def get_run_logs(run_id: int):
        return {'logs': []}

    @app.get('/api/runs/{run_id}')
    def get_run_detail(run_id: int, authorization: Optional[str] = None):
        return shared.get_run_detail_impl(run_id, authorization)
