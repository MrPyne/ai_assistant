def register(app, ctx):
    from . import shared_impls as shared
    from fastapi import HTTPException

    @app.post('/api/scheduler')
    def create_scheduler(body: dict, authorization: str = None):
        user_id = shared._user_from_token(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        return shared.create_scheduler_impl(body, user_id)

    @app.get('/api/scheduler')
    def list_scheduler(authorization: str = None):
        user_id = shared._user_from_token(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = shared._workspace_for_user(user_id)
        if not wsid:
            return []
        return shared.list_scheduler_impl(wsid)

    @app.put('/api/scheduler/{sid}')
    def update_scheduler(sid: int, body: dict, authorization: str = None):
        user_id = shared._user_from_token(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = shared._workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        return shared.update_scheduler_impl(sid, body, wsid)

    @app.delete('/api/scheduler/{sid}')
    def delete_scheduler(sid: int, authorization: str = None):
        user_id = shared._user_from_token(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = shared._workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        return shared.delete_scheduler_impl(sid, wsid)
