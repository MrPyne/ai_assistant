def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    SessionLocal = common['SessionLocal']
    models = common['models']
    _users = common['users'] if 'users' in common else common.get('_users')
    _workspaces = common['workspaces'] if 'workspaces' in common else common.get('_workspaces')
    _next = common['_next']
    _workspace_for_user = common['_workspace_for_user']
    _add_audit = common['_add_audit']
    logger = common['logger']
    encrypt_value = common['encrypt_value']

    # Ensure console logging is available for easier debugging in development
    try:
        import logging, sys

        def _ensure_console_handler(log):
            # Add a StreamHandler writing to stdout so logs also appear on the console.
            # Use a guard attribute on the logger to avoid adding duplicate handlers on repeated register calls.
            try:
                if not getattr(log, '_console_handler_added', False):
                    ch = logging.StreamHandler(sys.stdout)
                    ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
                    ch.setLevel(logging.DEBUG)
                    log.addHandler(ch)
                    setattr(log, '_console_handler_added', True)
            except Exception:
                # fall back to non-stdout StreamHandler if something odd happens
                try:
                    if not getattr(log, '_console_handler_added', False):
                        ch = logging.StreamHandler()
                        ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
                        ch.setLevel(logging.DEBUG)
                        log.addHandler(ch)
                        setattr(log, '_console_handler_added', True)
                except Exception:
                    pass

        try:
            _ensure_console_handler(logger)
            # Also ensure the root logger has a handler so messages propagate to console in different configs.
            root = logging.getLogger()
            _ensure_console_handler(root)
        except Exception:
            pass

        # Set a sensible default level for development debugging
        try:
            logger.setLevel(logging.DEBUG)
            logging.getLogger().setLevel(logging.DEBUG)
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
            try:
                logger.debug("create_secret unauthorized authorization=%r", authorization)
            except Exception:
                pass
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        # If no workspace was found via the helper, attempt to create one directly
        # using the DB helpers (SessionLocal/models) when available. This covers
        # cases where a workspace migration was recently added and older users
        # don't yet have a workspace record.
        if not wsid:
            try:
                logger.info("create_secret: no workspace found via helper for user %r, attempting DB create", user_id)
            except Exception:
                pass
            try:
                if SessionLocal is not None and models is not None:
                    db = SessionLocal()
                    try:
                        user = db.query(models.User).filter(models.User.id == user_id).first()
                        name = f"{getattr(user, 'email', None)}-workspace" if user and getattr(user, 'email', None) else f'user-{user_id}-workspace'
                        new_ws = models.Workspace(name=name, owner_id=user_id)
                        db.add(new_ws)
                        db.commit()
                        db.refresh(new_ws)
                        wsid = new_ws.id
                        try:
                            logger.info("create_secret: created workspace %s for user %s", wsid, user_id)
                        except Exception:
                            pass
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
        if not wsid:
            try:
                logger.info("create_secret no workspace for user %r", user_id)
            except Exception:
                pass
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

            # Log creation for easier debugging (does not log the secret value)
            try:
                logger.info("create_secret id=%s name=%s created_by=%s workspace=%s", s.id, name, user_id, wsid)
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
            try:
                logger.debug("list_secrets unauthorized authorization=%r", authorization)
            except Exception:
                pass
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        try:
            logger.debug("list_secrets resolved workspace=%r", wsid)
        except Exception:
            pass
        if not wsid:
            try:
                logger.info("list_secrets: no workspace for user %s (resolved_user=%s)", user_id, user_id)
            except Exception:
                pass
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
            # For easier debugging, also log the list of secrets (ids and names only)
            try:
                if out:
                    logger.info("list_secrets found %d secrets in workspace %s", len(out), wsid)
                    for s in out:
                        try:
                            logger.info("secret id=%s name=%s created_by=%s", s.get('id'), s.get('name'), s.get('created_by'))
                        except Exception:
                            pass
                else:
                    logger.info("list_secrets found 0 secrets in workspace %s", wsid)
            except Exception:
                pass
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
            try:
                logger.debug("delete_secret unauthorized authorization=%r", authorization)
            except Exception:
                pass
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            try:
                logger.info("delete_secret no workspace for user %r", user_id)
            except Exception:
                pass
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

            # Log deletion for easier debugging
            try:
                logger.info("delete_secret id=%s name=%s deleted_by=%s workspace=%s", sid, getattr(s, 'name', None), user_id, wsid)
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
