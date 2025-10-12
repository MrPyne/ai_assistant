def register(app, ctx):
    """Auth routes extracted from original app_impl."""
    from . import _shared as shared
    try:
        from fastapi import Depends
        can_use_depends = True
    except Exception:
        can_use_depends = False

    if can_use_depends:
        from fastapi import Depends
        from ..database import get_db

        @app.post('/api/auth/register')
        def _auth_register(body: dict, db=Depends(get_db)):
            return shared.auth_register_db(body, db)
    else:
        @app.post('/api/auth/register')
        def _auth_register(body: dict):
            return shared.auth_register_fallback(body)

    @app.post('/api/auth/login')
    def _auth_login(body: dict):
        return shared.auth_login(body)

    @app.post('/api/auth/resend')
    def _auth_resend(body: dict):
        return shared.auth_resend(body)
