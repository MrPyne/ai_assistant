def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    SessionLocal = common['SessionLocal']
    models = common['models']
    _DB_AVAILABLE = common['_DB_AVAILABLE']
    _users = common['_users']
    _workspaces = common['_workspaces']
    _secrets = common['_secrets']
    _next = common['_next']
    _workspace_for_user = common['_workspace_for_user']
    _add_audit = common['_add_audit']
    logger = common['logger']
    _FASTAPI_HEADERS = common['_FASTAPI_HEADERS']
    encrypt_value = common['encrypt_value']

    try:
        from fastapi import HTTPException, Header
        from fastapi.responses import JSONResponse
    except Exception:
        # minimal stand-ins are provided by api_common's init_ctx
        from backend.routes.api_common import HTTPException, Header, JSONResponse  # type: ignore

    # create
    if _FASTAPI_HEADERS:
        @app.post('/api/secrets')
        def create_secret(body: dict, authorization: str = Header(None)):
            return create_secret_impl(body, authorization)
    else:
        @app.post('/api/secrets')
        def create_secret(body: dict, authorization: str = None):
            return create_secret_impl(body, authorization)

    def create_secret_impl(body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400, detail='Workspace not found')
        name = body.get('name')
        value = body.get('value')
        if not name or value is None:
            return JSONResponse(status_code=400, content={'detail': 'name and value required'})
        if _DB_AVAILABLE:
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
        sid = _next.get('secret', 1)
        _next['secret'] = sid + 1
        _secrets[sid] = {'workspace_id': wsid, 'name': name, 'value': value}
        try:
            _add_audit(wsid, user_id, 'create_secret', object_type='secret', object_id=sid, detail=name)
        except Exception:
            pass
        return {'id': sid}

    # list
    if _FASTAPI_HEADERS:
        @app.get('/api/secrets')
        def list_secrets(authorization: str = Header(None)):
            return list_secrets_impl(authorization)
    else:
        @app.get('/api/secrets')
        def list_secrets(authorization: str = None):
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
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                rows = db.query(models.Secret).filter(models.Secret.workspace_id == wsid).all()
                try:
                    logger.debug("list_secrets DB rows=%d", len(rows))
                except Exception:
                    pass
                out = []
                for r in rows:
                    out.append({'id': r.id, 'workspace_id': r.workspace_id, 'name': r.name, 'created_at': getattr(r, 'created_at', None)})
                return out
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        items = []
        for sid, s in _secrets.items():
            if s.get('workspace_id') == wsid:
                obj = dict(s)
                obj['id'] = sid
                obj.pop('value', None)
                items.append(obj)
        try:
            logger.debug("list_secrets in-memory items=%d", len(items))
        except Exception:
            pass
        return items

    # delete
    if _FASTAPI_HEADERS:
        @app.delete('/api/secrets/{sid}')
        def delete_secret(sid: int, authorization: str = Header(None)):
            return delete_secret_impl(sid, authorization)
    else:
        @app.delete('/api/secrets/{sid}')
        def delete_secret(sid: int, authorization: str = None):
            return delete_secret_impl(sid, authorization)

    def delete_secret_impl(sid: int, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        if _DB_AVAILABLE:
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
        s = _secrets.get(sid)
        if not s or s.get('workspace_id') != wsid:
            raise HTTPException(status_code=404)
        del _secrets[sid]
        try:
            _add_audit(wsid, user_id, 'delete_secret', object_type='secret', object_id=sid)
        except Exception:
            pass
        return {'status': 'deleted'}
