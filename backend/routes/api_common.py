def init_ctx(ctx):
    """Return a dictionary of commonly-used runtime values for route modules."""
    SessionLocal = ctx.get('SessionLocal')
    models = ctx.get('models')
    _DB_AVAILABLE = ctx.get('_DB_AVAILABLE')
    _users = ctx.get('_users')
    _workspaces = ctx.get('_workspaces')
    _secrets = ctx.get('_secrets')
    _providers = ctx.get('_providers')
    _workflows = ctx.get('_workflows')
    _webhooks = ctx.get('_webhooks')
    _next = ctx.get('_next')
    _add_audit = ctx.get('_add_audit')
    _workspace_for_user = ctx.get('_workspace_for_user')

    # logger fallback
    import logging
    logger = ctx.get('logger') if ctx.get('logger') is not None else logging.getLogger('backend.api_routes')

    # FastAPI header helpers
    try:
        from fastapi import Header, Request  # type: ignore
        from fastapi import HTTPException  # type: ignore
        from fastapi.responses import JSONResponse  # type: ignore
        _FASTAPI_HEADERS = True
    except Exception:
        # minimal stand-ins
        class HTTPException(Exception):
            def __init__(self, status_code: int = 500, detail: str = None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class JSONResponse:  # very small stand-in used by tests
            def __init__(self, content=None, status_code: int = 200):
                self.content = content
                self.status_code = status_code

        def Header(default=None, **kwargs):
            return default

        Request = None
        _FASTAPI_HEADERS = False

    # crypto helpers
    try:
        from ..crypto import encrypt_value, decrypt_value
    except Exception:
        encrypt_value = None
        decrypt_value = None

    # ensure fallbacks for token/workspace/audit
    # Prefer DB-backed implementations using ctx's SessionLocal and models when
    # available. This ensures workspace creation on first-use and audit logging
    # work even when the top-level ctx wasn't fully populated by app_impl.
    try:
        from ..app_stub import _user_from_token as _stub_user_from_token
        if not callable(ctx.get('_user_from_token')):
            ctx['_user_from_token'] = _stub_user_from_token
    except Exception:
        if not callable(ctx.get('_user_from_token')):
            ctx['_user_from_token'] = (lambda authorization=None: None)

    if not callable(ctx.get('_workspace_for_user')):
        def _workspace_for_user_db(user_id):
            SessionLocal_local = ctx.get('SessionLocal')
            models_local = ctx.get('models')
            # Prefer DB-backed workspace lookup/creation when possible
            if SessionLocal_local and models_local:
                try:
                    db = SessionLocal_local()
                    try:
                        ws = db.query(models_local.Workspace).filter(models_local.Workspace.owner_id == user_id).first()
                        if ws:
                            return ws.id
                        # No workspace found; create one for older users
                        try:
                            user = db.query(models_local.User).filter(models_local.User.id == user_id).first()
                            name = f"{getattr(user, 'email', None)}-workspace" if user and getattr(user, 'email', None) else f'user-{user_id}-workspace'
                            new_ws = models_local.Workspace(name=name, owner_id=user_id)
                            db.add(new_ws)
                            db.commit()
                            db.refresh(new_ws)
                            return new_ws.id
                        except Exception:
                            try:
                                db.rollback()
                            except Exception:
                                pass
                            return None
                    except Exception:
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        return None
                    finally:
                        try:
                            db.close()
                        except Exception:
                            pass
                except Exception:
                    pass

            # Fallback to in-memory workspace store
            try:
                wstore = ctx.get('_workspaces') or {}
                for wid, w in (wstore or {}).items():
                    if w.get('owner_id') == user_id:
                        return wid
                if wstore:
                    return list(wstore.keys())[0]
            except Exception:
                pass
            return None
        ctx['_workspace_for_user'] = _workspace_for_user_db

    if not callable(ctx.get('_add_audit')):
        def _add_audit_db(workspace_id, user_id, action, **kwargs):
            SessionLocal_local = ctx.get('SessionLocal')
            models_local = ctx.get('models')
            if SessionLocal_local and models_local:
                try:
                    db = SessionLocal_local()
                    try:
                        al = models_local.AuditLog(workspace_id=workspace_id, user_id=user_id, action=action, object_type=kwargs.get('object_type'), object_id=kwargs.get('object_id'), detail=kwargs.get('detail'))
                        db.add(al)
                        db.commit()
                    except Exception:
                        try:
                            db.rollback()
                        except Exception:
                            pass
                    finally:
                        try:
                            db.close()
                        except Exception:
                            pass
                except Exception:
                    pass
            # otherwise no-op
            return None
        ctx['_add_audit'] = _add_audit_db

    # refresh locals
    _workspace_for_user = ctx.get('_workspace_for_user')
    _add_audit = ctx.get('_add_audit')

    return {
        'SessionLocal': SessionLocal,
        'models': models,
        '_DB_AVAILABLE': _DB_AVAILABLE,
        '_users': _users,
        '_workspaces': _workspaces,
        '_secrets': _secrets,
        '_providers': _providers,
        '_workflows': _workflows,
        '_webhooks': _webhooks,
        '_next': _next,
        '_add_audit': _add_audit,
        '_workspace_for_user': _workspace_for_user,
        'logger': logger,
        '_FASTAPI_HEADERS': _FASTAPI_HEADERS,
        'encrypt_value': encrypt_value,
        'decrypt_value': decrypt_value,
    }