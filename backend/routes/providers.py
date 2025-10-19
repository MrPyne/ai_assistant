def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    SessionLocal = common['SessionLocal']
    models = common['models']
    _DB_AVAILABLE = common['_DB_AVAILABLE']
    _users = common['_users']
    _workspaces = common['_workspaces']
    _secrets = common['_secrets']
    _providers = common['_providers']
    _next = common['_next']
    _workspace_for_user = common['_workspace_for_user']
    _add_audit = common['_add_audit']
    logger = common['logger']
    _FASTAPI_HEADERS = common['_FASTAPI_HEADERS']
    encrypt_value = common['encrypt_value']
    decrypt_value = common['decrypt_value']

    try:
        from fastapi import HTTPException, Header
        from fastapi.responses import JSONResponse
    except Exception:
        from backend.routes.api_common import HTTPException, Header, JSONResponse  # type: ignore

    # get single provider
    if _FASTAPI_HEADERS:
        @app.get('/api/providers/{pid}')
        def get_provider(pid: int, authorization: str = Header(None)):
            return get_provider_impl(pid, authorization)
    else:
        @app.get('/api/providers/{pid}')
        def get_provider(pid: int, authorization: str = None):
            return get_provider_impl(pid, authorization)

    def get_provider_impl(pid: int, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization) if authorization is not None else None
        if not user_id:
            if _users:
                user_id = list(_users.keys())[0]
            else:
                raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                p = db.query(models.Provider).filter(models.Provider.id == pid).first()
                if not p or p.workspace_id != wsid:
                    raise HTTPException(status_code=404)
                return {'id': p.id, 'workspace_id': p.workspace_id, 'type': p.type, 'secret_id': getattr(p, 'secret_id', None), 'config': getattr(p, 'config', None), 'last_tested_at': getattr(p, 'last_tested_at', None)}
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        p = _providers.get(pid)
        if not p or p.get('workspace_id') != wsid:
            raise HTTPException(status_code=404)
        out = dict(p)
        out['id'] = pid
        return out

    # update provider
    if _FASTAPI_HEADERS:
        @app.put('/api/providers/{pid}')
        def update_provider(pid: int, body: dict, authorization: str = Header(None)):
            return update_provider_impl(pid, body, authorization)
    else:
        @app.put('/api/providers/{pid}')
        def update_provider(pid: int, body: dict, authorization: str = None):
            return update_provider_impl(pid, body, authorization)

    def update_provider_impl(pid: int, body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization) if authorization is not None else None
        if not user_id:
            if _users:
                user_id = list(_users.keys())[0]
            else:
                raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        inline_secret = body.get('secret') if isinstance(body, dict) else None
        secret_id = body.get('secret_id')
        if inline_secret is not None:
            try:
                import json as _json
                secret_value = _json.dumps(inline_secret)
            except Exception:
                return JSONResponse(status_code=400, content={'detail': 'invalid secret payload'})
            if _DB_AVAILABLE:
                try:
                    db = SessionLocal()
                    enc = secret_value
                    try:
                        if encrypt_value is not None:
                            enc = encrypt_value(secret_value)
                    except Exception:
                        enc = secret_value
                    s = models.Secret(workspace_id=wsid, name=f"provider:update", encrypted_value=enc, created_by=user_id)
                    db.add(s)
                    db.commit()
                    db.refresh(s)
                    secret_id = s.id
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
            else:
                sid = _next.get('secret', 1)
                _next['secret'] = sid + 1
                _secrets[sid] = {'workspace_id': wsid, 'name': f"provider:update", 'value': secret_value}
                secret_id = sid
        if secret_id is not None:
            if _DB_AVAILABLE:
                try:
                    db = SessionLocal()
                    s = db.query(models.Secret).filter(models.Secret.id == secret_id, models.Secret.workspace_id == wsid).first()
                    if not s:
                        return JSONResponse(status_code=400, content={'detail': 'secret_id not found in workspace'})
                finally:
                    try:
                        db.close()
                    except Exception:
                        pass
            else:
                s = _secrets.get(secret_id)
                if not s or s.get('workspace_id') != wsid:
                    return JSONResponse(status_code=400, content={'detail': 'secret_id not found in workspace'})
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                p = db.query(models.Provider).filter(models.Provider.id == pid).first()
                if not p or p.workspace_id != wsid:
                    raise HTTPException(status_code=404)
                if 'type' in body:
                    p.type = body.get('type')
                if secret_id is not None:
                    p.secret_id = secret_id
                if 'config' in body:
                    p.config = body.get('config')
                db.add(p)
                db.commit()
                try:
                    _add_audit(wsid, user_id, 'update_provider', object_type='provider', object_id=p.id, detail=p.type)
                except Exception:
                    pass
                return {'id': p.id, 'workspace_id': p.workspace_id, 'type': p.type, 'secret_id': getattr(p, 'secret_id', None)}
            except HTTPException:
                raise
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                return JSONResponse(status_code=500, content={'detail': 'failed to update provider'})
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        p = _providers.get(pid)
        if not p or p.get('workspace_id') != wsid:
            raise HTTPException(status_code=404)
        if 'type' in body:
            p['type'] = body.get('type')
        if secret_id is not None:
            p['secret_id'] = secret_id
        if 'config' in body:
            p['config'] = body.get('config')
        try:
            _add_audit(wsid, user_id, 'update_provider', object_type='provider', object_id=pid, detail=p.get('type'))
        except Exception:
            pass
        return {'id': pid, 'workspace_id': p.get('workspace_id'), 'type': p.get('type'), 'secret_id': p.get('secret_id')}

    # provider create/list
    if _FASTAPI_HEADERS:
        @app.post('/api/providers')
        def create_provider(body: dict, authorization: str = Header(None)):
            return create_provider_impl(body, authorization)
    else:
        @app.post('/api/providers')
        def create_provider(body: dict, authorization: str = None):
            return create_provider_impl(body, authorization)

    def create_provider_impl(body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            if _users:
                user_id = list(_users.keys())[0]
            else:
                raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        secret_id = body.get('secret_id')
        inline_secret = body.get('secret')
        if inline_secret is not None:
            try:
                import json as _json
                secret_value = _json.dumps(inline_secret)
            except Exception:
                return JSONResponse(status_code=400, content={'detail': 'invalid secret payload'})
            if _DB_AVAILABLE:
                try:
                    db = SessionLocal()
                    enc = secret_value
                    try:
                        if encrypt_value is not None:
                            enc = encrypt_value(secret_value)
                    except Exception:
                        enc = secret_value
                    s = models.Secret(workspace_id=wsid, name=f"provider:{body.get('type')}", encrypted_value=enc, created_by=user_id)
                    db.add(s)
                    db.commit()
                    db.refresh(s)
                    secret_id = s.id
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
            else:
                sid = _next.get('secret', 1)
                _next['secret'] = sid + 1
                _secrets[sid] = {'workspace_id': wsid, 'name': f"provider:{body.get('type')}", 'value': secret_value}
                secret_id = sid
        if secret_id is not None:
            if _DB_AVAILABLE:
                try:
                    db = SessionLocal()
                    s = db.query(models.Secret).filter(models.Secret.id == secret_id, models.Secret.workspace_id == wsid).first()
                    if not s:
                        raise HTTPException(status_code=400, detail='secret_id not found in workspace')
                finally:
                    try:
                        db.close()
                    except Exception:
                        pass
            else:
                s = _secrets.get(secret_id)
                if not s or s.get('workspace_id') != wsid:
                    raise HTTPException(status_code=400, detail='secret_id not found in workspace')
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                p = models.Provider(workspace_id=wsid, type=body.get('type'), secret_id=secret_id, config=body.get('config'))
                db.add(p)
                db.commit()
                db.refresh(p)
                try:
                    _add_audit(wsid, user_id, 'create_provider', object_type='provider', object_id=p.id, detail=body.get('type'))
                except Exception:
                    pass
                return {'id': p.id, 'workspace_id': p.workspace_id, 'type': p.type, 'secret_id': p.secret_id}
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                return JSONResponse(status_code=500, content={'detail': 'failed to create provider'})
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        pid = _next.get('provider', 1)
        _next['provider'] = pid + 1
        _providers[pid] = {'workspace_id': wsid, 'type': body.get('type'), 'secret_id': secret_id, 'config': body.get('config')}
        return {'id': pid, 'workspace_id': wsid, 'type': body.get('type'), 'secret_id': secret_id}

    if _FASTAPI_HEADERS:
        @app.get('/api/providers')
        def list_providers(authorization: str = Header(None)):
            return list_providers_impl(authorization)
    else:
        @app.get('/api/providers')
        def list_providers(authorization: str = None):
            return list_providers_impl(authorization)

    def list_providers_impl(authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        try:
            logger.debug("list_providers called authorization=%r resolved_user=%r", authorization, user_id)
        except Exception:
            pass
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        try:
            logger.debug("list_providers resolved workspace=%r", wsid)
        except Exception:
            pass
        if not wsid:
            return []
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                rows = db.query(models.Provider).filter(models.Provider.workspace_id == wsid).all()
                try:
                    logger.debug("list_providers DB rows=%d", len(rows))
                except Exception:
                    pass
                out = []
                for r in rows:
                    out.append({'id': r.id, 'workspace_id': r.workspace_id, 'type': r.type, 'secret_id': getattr(r, 'secret_id', None), 'last_tested_at': getattr(r, 'last_tested_at', None)})
                return out
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        items = []
        for pid, p in _providers.items():
            if p.get('workspace_id') == wsid:
                obj = dict(p)
                obj['id'] = pid
                items.append(obj)
        try:
            logger.debug("list_providers in-memory items=%d", len(items))
        except Exception:
            pass
        return items
