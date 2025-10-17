def register(app, ctx):
    from . import shared_impls as shared
    try:
        from fastapi import HTTPException, Header
        from typing import Optional
        _FASTAPI = True
    except Exception:
        # provide minimal stand-ins when FastAPI is not available (tests use this)
        class HTTPException(Exception):
            def __init__(self, status_code: int = 500, detail: str = None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        def Header(default=None, **kwargs):
            return default

        from typing import Optional  # still available in stdlib
        _FASTAPI = False

    @app.post('/api/scheduler')
    def create_scheduler(body: dict, authorization: Optional[str] = Header(None)):
        # Authorization header is provided as a header; use FastAPI Header to bind it
        user_id = shared._user_from_token(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        return shared.create_scheduler_impl(body, user_id)

    @app.get('/api/scheduler')
    def list_scheduler(authorization: Optional[str] = Header(None)):
        user_id = shared._user_from_token(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = shared._workspace_for_user(user_id)
        if not wsid:
            return []
        return shared.list_scheduler_impl(wsid)

    @app.put('/api/scheduler/{sid}')
    def update_scheduler(sid: int, body: dict, authorization: Optional[str] = Header(None)):
        user_id = shared._user_from_token(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = shared._workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        return shared.update_scheduler_impl(sid, body, wsid)

    @app.delete('/api/scheduler/{sid}')
    def delete_scheduler(sid: int, authorization: Optional[str] = Header(None)):
        user_id = shared._user_from_token(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = shared._workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        return shared.delete_scheduler_impl(sid, wsid)
