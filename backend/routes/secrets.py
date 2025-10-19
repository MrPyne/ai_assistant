def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    SessionLocal = common['SessionLocal']
    models = common['models']
    _users = common['_users']
    _workspaces = common['_workspaces']
    _next = common['_next']
    _workspace_for_user = common['_workspace_for_user']
    _add_audit = common['_add_audit']
    logger = common['logger']
    encrypt_value = common['encrypt_value']

    # Ensure console logging is available for easier debugging in development
    try:
        import logging, sys

        # Add a StreamHandler writing to stdout so logs also appear on the console.
        # Use a guard attribute on the logger to avoid adding duplicate handlers on repeated register calls.
        try:
            if not getattr(logger, '_console_handler_added', False):
                ch = logging.StreamHandler(sys.stdout)
                ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
                ch.setLevel(logging.DEBUG)
                logger.addHandler(ch)
                setattr(logger, '_console_handler_added', True)
        except Exception:
            # fall back to non-stdout StreamHandler if something odd happens
            try:
                if not getattr(logger, '_console_handler_added', False):
                    ch = logging.StreamHandler()
                    ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
                    ch.setLevel(logging.DEBUG)
                    logger.addHandler(ch)
                    setattr(logger, '_console_handler_added', True)
            except Exception:
                pass

        # Set a sensible default level for development debugging
        try:
            logger.setLevel(logging.DEBUG)
        except Exception:
            pass
    except Exception:
        pass

    # always use FastAPI request headers and DB-backed secrets
    from fastapi import HTTPException, Header
    from fastapi.responses import JSONResponse
    from typing import List
    from backend.schemas import SecretCreate, SecretOut

    # create
    @app.post('/api/secrets')
    def create_secret(body: SecretCreate, authorization: str = Header(None)):
        return create_secret_impl(body, authorization)

    def create_secret_impl(body: SecretCreate, authorization: str = None):
        name = getattr(body, 'name', None)
        value = getattr(body, 'value', None)

        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400, detail='Workspace not found')
        if not name or value is None:
            return JSONResponse(status_code=400, content={'detail': 'name and value required'})

        try:
            db = SessionLocal()
            enc = value
            try:
                if encrypt_value is not None:
                    enc = encrypt_value(value)
            except Exception:
                enc = value
            s = models.Secret(workspace_id=wsid, name=name, encrypted_value=enc, created_by=user_id)
            db.add(s)
            db.commit()
            db.refresh(s)
            try:
                _add_audit(wsid, user_id, 'create_secret', object_type='secret', object_id=s.id, detail=name)
            except Exception:
                pass
            return {'id': s.id}
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return JSONResponse(status_code=500, content={'detail': 'failed to create secret'})
        finally:
            try:
                db.close()
            except Exception:
                pass

    # list
    @app.get('/api/secrets')
    def list_secrets(authorization: str = Header(None)):
        return list_secrets_impl(authorization)

    def list_secrets_impl(authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        try:
            logger.debug("list_secrets called authorization=%r resolved_user=%r", authorization, user_id)
        except Exception:
            pass
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        try:
            logger.debug("list_secrets resolved workspace=%r", wsid)
        except Exception:
            pass
        if not wsid:
            return []

        try:
            db = SessionLocal()
            rows = db.query(models.Secret).filter(models.Secret.workspace_id == wsid).all()
            try:
                logger.debug("list_secrets DB rows=%d", len(rows))
            except Exception:
                pass
            out = []
            for r in rows:
                out.append({'id': r.id, 'workspace_id': r.workspace_id, 'name': r.name, 'created_by': getattr(r, 'created_by', None), 'created_at': getattr(r, 'created_at', None)})
            return out
        finally:
            try:
                db.close()
            except Exception:
                pass

    # delete
    @app.delete('/api/secrets/{sid}')
    def delete_secret(sid: int, authorization: str = Header(None)):
        return delete_secret_impl(sid, authorization)

    def delete_secret_impl(sid: int, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)

        try:
            db = SessionLocal()
            s = db.query(models.Secret).filter(models.Secret.id == sid).first()
            if not s or s.workspace_id != wsid:
                raise HTTPException(status_code=404)
            db.delete(s)
            db.commit()
            try:
                _add_audit(wsid, user_id, 'delete_secret', object_type='secret', object_id=sid)
            except Exception:
                pass
            return {'status': 'deleted'}
        except HTTPException:
            # pass through HTTPExceptions raised above
            raise
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            raise HTTPException(status_code=500)
        finally:
            try:
                db.close()
            except Exception:
                pass
