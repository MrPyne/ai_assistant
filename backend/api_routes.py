def register(app, ctx):
    """Register missing API routes (secrets, providers, workflows, webhooks, /me).
    This is kept separate to allow refactoring of app_impl into smaller modules.
    The `ctx` dict is expected to contain the common globals from app_impl
    (SessionLocal, models, _DB_AVAILABLE, and the in-memory stores).
    """
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
    import os
    import logging

    # lightweight logger: prefer ctx-provided logger when available so test harness
    # or app_impl can inject a configured logger. Fall back to module logger.
    logger = ctx.get('logger') if ctx.get('logger') is not None else logging.getLogger('backend.api_routes')

    # Ensure minimal helper fallbacks so endpoints do not crash when a richer
    # runtime context (app_impl) did not populate these hooks. These fallbacks
    # mirror the conservative behaviour used in backend/app._maybe_register_routes
    # and avoid TypeError: 'NoneType' object is not callable when calling
    # ctx.get('_user_from_token')(authorization).
    if not callable(ctx.get('_user_from_token')):
        try:
            from .app_stub import _user_from_token as _stub_user_from_token
            ctx['_user_from_token'] = _stub_user_from_token
        except Exception:
            ctx['_user_from_token'] = (lambda authorization=None: None)

    if not callable(ctx.get('_workspace_for_user')):
        def _default_workspace_for_user(user_id):
            # Try to resolve from an in-memory _workspaces store if present
            try:
                wstore = ctx.get('_workspaces') or {}
                for wid, w in (wstore or {}).items():
                    if w.get('owner_id') == user_id:
                        return wid
            except Exception:
                pass
            # fall back to any existing workspace id or None
            try:
                wstore = ctx.get('_workspaces') or {}
                if wstore:
                    return list(wstore.keys())[0]
            except Exception:
                pass
            return None

        ctx['_workspace_for_user'] = _default_workspace_for_user

    if not callable(ctx.get('_add_audit')):
        ctx['_add_audit'] = (lambda workspace_id, user_id, action, **kwargs: None)

    # Ensure local references reflect any fallbacks we just installed so
    # functions defined below use callables instead of stale None values.
    _workspace_for_user = ctx.get('_workspace_for_user')
    _add_audit = ctx.get('_add_audit')

    # Normalize HTTPException/JSONResponse for lightweight imports
    try:
        from fastapi import HTTPException  # type: ignore
        from fastapi.responses import JSONResponse  # type: ignore
        from fastapi import Header, Request  # type: ignore
        _FASTAPI_HEADERS = True
    except ImportError:
        class HTTPException(Exception):
            def __init__(self, status_code: int = 500, detail: str = None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class JSONResponse:  # very small stand-in used by tests
            def __init__(self, content=None, status_code: int = 200):
                self.content = content
                self.status_code = status_code
        # stand-ins so we can write unified route definitions below
        def Header(default=None, **kwargs):
            return default
        Request = None
        _FASTAPI_HEADERS = False

    # Helper: minimal encrypt/decrypt when DB-backed
    try:
        from .crypto import encrypt_value, decrypt_value
    except Exception:
        encrypt_value = None
        decrypt_value = None

    # /api/me
    # actual route function delegates to _me_impl; place decorator inside
    # the conditional so the decorator applies to a real function definition
    if _FASTAPI_HEADERS:
        @app.get('/api/me')
        def _me(authorization: str = Header(None)):
            return _me_impl(authorization)
    else:
        @app.get('/api/me')
        def _me(authorization: str = None):
            return _me_impl(authorization)

    # actual implementation delegated to a nested function so the signature
    # above gets the correct defaults for FastAPI vs the test stand-in
    def _me_impl(authorization: str = None):
        # Try to reuse app_impl helper _user_from_token via ctx if present
        _user_from_token = ctx.get('_user_from_token')
        uid = None
        try:
            uid = _user_from_token(authorization)
        except Exception:
            uid = None
        if not uid:
            # FastAPI usually returns 401; keep simple behaviour
            raise HTTPException(status_code=401)

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                u = db.query(models.User).filter(models.User.id == uid).first()
                if not u:
                    raise HTTPException(status_code=404)
                # find workspace
                ws = db.query(models.Workspace).filter(models.Workspace.owner_id == u.id).first()
                return {'email': u.email, 'workspace': ws.name if ws is not None else None}
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        # in-memory fallback
        u = _users.get(uid)
        if not u:
            raise HTTPException(status_code=404)
        # find workspace
        ws_name = None
        for wid, w in _workspaces.items():
            if w.get('owner_id') == uid:
                ws_name = w.get('name')
                break
        return {'email': u.get('email'), 'workspace': ws_name}

    # Secrets: POST /api/secrets, GET /api/secrets, DELETE /api/secrets/{id}
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
        # find workspace
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
                # encrypt value when possible
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
                # do not return plaintext value
                obj.pop('value', None)
                items.append(obj)
        try:
            logger.debug("list_secrets in-memory items=%d", len(items))
        except Exception:
            pass
        return items

    # GET single provider (returns provider metadata without plaintext secret)
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

    # Update provider: PUT /api/providers/{pid}
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

        # validate secret ownership if provided
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

    # Provider schema discovery: GET /api/provider_schema/{type}
    if _FASTAPI_HEADERS:
        @app.get('/api/provider_schema/{ptype}')
        def get_provider_schema(ptype: str, authorization: str = Header(None)):
            return get_provider_schema_impl(ptype, authorization)
    else:
        @app.get('/api/provider_schema/{ptype}')
        def get_provider_schema(ptype: str, authorization: str = None):
            return get_provider_schema_impl(ptype, authorization)

    def get_provider_schema_impl(ptype: str, authorization: str = None):
        # minimal auth required; allow unauthenticated for discovery in some flows
        # return provider-specific JSON Schema + UI hints
        schemas = {
            's3': {
                'title': 'AWS S3',
                'type': 'object',
                'properties': {
                    'access_key': {'type': 'string'},
                    'secret_key': {'type': 'string', 'ui:widget': 'password'},
                    'session_token': {'type': 'string', 'ui:widget': 'password'},
                    'region': {'type': 'string'}
                },
                'required': ['access_key', 'secret_key']
            },
            'smtp': {
                'title': 'SMTP',
                'type': 'object',
                'properties': {
                    'host': {'type': 'string'},
                    'port': {'type': 'number'},
                    'username': {'type': 'string'},
                    'password': {'type': 'string', 'ui:widget': 'password'},
                    'use_tls': {'type': 'boolean'}
                },
                'required': ['host']
            }
        }
        return schemas.get(ptype, {'title': ptype, 'type': 'object'})

    # Provider types list: GET /api/provider_types
    if _FASTAPI_HEADERS:
        @app.get('/api/provider_types')
        def list_provider_types(authorization: str = Header(None)):
            return list_provider_types_impl(authorization)
    else:
        @app.get('/api/provider_types')
        def list_provider_types(authorization: str = None):
            return list_provider_types_impl(authorization)

    def list_provider_types_impl(authorization: str = None):
        # allow unauthenticated discovery
        return ['s3', 'smtp', 'openai', 'gcp', 'azure']

    # Provider models list: GET /api/provider_models/{ptype}
    if _FASTAPI_HEADERS:
        @app.get('/api/provider_models/{ptype}')
        def list_provider_models(ptype: str, authorization: str = Header(None)):
            return list_provider_models_impl(ptype, authorization)
    else:
        @app.get('/api/provider_models/{ptype}')
        def list_provider_models(ptype: str, authorization: str = None):
            return list_provider_models_impl(ptype, authorization)

    def list_provider_models_impl(ptype: str, authorization: str = None):
        # Provide a minimal provider-model discovery endpoint used by the UI.
        # This does not require a provider instance and returns a conservative
        # set of models per provider type. In a production system this could
        # call the upstream vendor API (OpenAI/Ollama) to list available models
        # and cache results.
        p = (ptype or '').lower()
        if p == 'openai':
            return ['gpt-4', 'gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo', 'gpt-3.5-turbo-16k']
        if p == 'ollama':
            return ['llama', 'mistral', 'llama2']
        # fallback: empty list
        return []

    # Node schema discovery: GET /api/node_schema/{label}
    if _FASTAPI_HEADERS:
        @app.get('/api/node_schema/{label}')
        def get_node_schema(label: str, authorization: str = Header(None)):
            return get_node_schema_impl(label, authorization)
    else:
        @app.get('/api/node_schema/{label}')
        def get_node_schema(label: str, authorization: str = None):
            return get_node_schema_impl(label, authorization)

    def get_node_schema_impl(label: str, authorization: str = None):
        # minimal auth: allow unauthenticated discovery
        try:
            from .node_schemas import get_node_json_schema
        except Exception:
            def get_node_json_schema(l: str):
                return {'type': 'object'}
        schema = get_node_json_schema(label)
        return schema or {'type': 'object'}

    # Templates: GET /api/templates
    # Frontend expects a list of template objects. This endpoint is optional —
    # if no remote templates are provided the frontend will fall back to built-in
    # templates. We expose any templates present in ctx['_templates'] or return
    # a small default starter template so the UI works out of the box.
    if _FASTAPI_HEADERS:
        @app.get('/api/templates')
        def list_templates(authorization: str = Header(None)):
            return list_templates_impl(authorization)
    else:
        @app.get('/api/templates')
        def list_templates(authorization: str = None):
            return list_templates_impl(authorization)

    def list_templates_impl(authorization: str = None):
        # optional auth: try to validate token but allow unauthenticated access
        try:
            _ = ctx.get('_user_from_token')(authorization)
        except Exception:
            pass
        # prefer templates provided by the runtime/context
        t = ctx.get('_templates')
        if t and isinstance(t, list):
            return t

        # Attempt to load templates from the server-side templates directory.
        # This keeps the frontend reliant on /api/templates instead of public files.
        try:
            import json as _json
        except Exception:
            _json = None

        templates_out = []
        try:
            # directory next to this file: backend/templates
            templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
            if not os.path.isdir(templates_dir):
                # fallback for dev setups where frontend files still exist
                templates_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'public', 'templates'))

            if os.path.isdir(templates_dir):
                for fn in sorted(os.listdir(templates_dir)):
                    if not fn.lower().endswith('.json'):
                        continue
                    p = os.path.join(templates_dir, fn)
                    try:
                        with open(p, 'r', encoding='utf-8') as fh:
                            if _json is not None:
                                obj = _json.load(fh)
                            else:
                                # minimal fallback: use eval (very unlikely)
                                obj = eval(fh.read())
                        if isinstance(obj, dict):
                            templates_out.append(obj)
                    except Exception:
                        # ignore malformed files
                        continue
        except Exception:
            templates_out = []

        if templates_out:
            return templates_out

        # final fallback: a tiny starter template so the UI still works
        return [
            {
                'id': 'starter-1',
                'title': 'HTTP -> LLM',
                'description': 'Simple pipeline: HTTP request -> LLM processing',
                'graph': {
                    'nodes': [
                        { 'id': 'n1', 'type': 'input', 'position': { 'x': 0, 'y': 0 }, 'data': { 'label': 'HTTP Trigger', 'config': {} } },
                        { 'id': 'n2', 'type': 'http', 'position': { 'x': 180, 'y': 0 }, 'data': { 'label': 'HTTP Request', 'config': { 'method': 'GET', 'url': 'https://api.example.com' } } },
                        { 'id': 'n3', 'type': 'llm', 'position': { 'x': 360, 'y': 0 }, 'data': { 'label': 'LLM', 'config': { 'model': 'gpt' } } },
                    ],
                    'edges': [ { 'id': 'e1', 'source': 'n1', 'target': 'n2' }, { 'id': 'e2', 'source': 'n2', 'target': 'n3' } ]
                }
            }
        ]

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

    # Providers: GET /api/providers, POST /api/providers
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
        # allow provider creation without an authenticated user for some client flows
        if not user_id:
            # fallback: if no user exists yet, try to default to first user in _users
            if _users:
                user_id = list(_users.keys())[0]
            else:
                raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)

        secret_id = body.get('secret_id')
        inline_secret = body.get('secret')
        # If an inline secret JSON object is provided, create a Secret and
        # attach it to the provider. This lets the frontend submit structured
        # credentials (e.g., AWS keys, session tokens) without a separate
        # secret creation step.
        if inline_secret is not None:
            # inline_secret should be serializable to a string; coerce to JSON
            try:
                import json as _json
                secret_value = _json.dumps(inline_secret)
            except Exception:
                return JSONResponse(status_code=400, content={'detail': 'invalid secret payload'})
            # create secret in DB or in-memory store
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
            # validate secret ownership
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
                    # audit provider creation
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

    # Workflows: GET /api/workflows, POST /api/workflows, PUT /api/workflows/{id}
    if _FASTAPI_HEADERS:
        @app.get('/api/workflows')
        def list_workflows(authorization: str = Header(None)):
            return list_workflows_impl(authorization)
    else:
        @app.get('/api/workflows')
        def list_workflows(authorization: str = None):
            return list_workflows_impl(authorization)

    # GET single workflow (returns full workflow including graph)
    if _FASTAPI_HEADERS:
        @app.get('/api/workflows/{wid}')
        def get_workflow(wid: int, authorization: str = Header(None)):
            return get_workflow_impl(wid, authorization)
    else:
        @app.get('/api/workflows/{wid}')
        def get_workflow(wid: int, authorization: str = None):
            return get_workflow_impl(wid, authorization)

    def get_workflow_impl(wid: int, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                wf = db.query(models.Workflow).filter(models.Workflow.id == wid).first()
                if not wf or wf.workspace_id != wsid:
                    raise HTTPException(status_code=404)
                return {'id': wf.id, 'workspace_id': wf.workspace_id, 'name': wf.name, 'description': wf.description, 'graph': getattr(wf, 'graph', None)}
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        wf = _workflows.get(wid)
        if not wf or wf.get('workspace_id') != wsid:
            raise HTTPException(status_code=404)
        out = dict(wf)
        out['id'] = wid
        return out

    def list_workflows_impl(authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        try:
            logger.debug("list_workflows called authorization=%r resolved_user=%r", authorization, user_id)
        except Exception:
            pass
        # allow unauthenticated list to return empty
        if not user_id:
            return []
        wsid = _workspace_for_user(user_id)
        try:
            logger.debug("list_workflows resolved workspace=%r", wsid)
        except Exception:
            pass
        if not wsid:
            return []
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                rows = db.query(models.Workflow).filter(models.Workflow.workspace_id == wsid).all()
                try:
                    logger.debug("list_workflows DB rows=%d", len(rows))
                except Exception:
                    pass
                out = []
                for r in rows:
                    out.append({'id': r.id, 'workspace_id': r.workspace_id, 'name': r.name, 'description': r.description})
                return out
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        items = []
        for wid, w in _workflows.items():
            if w.get('workspace_id') == wsid:
                obj = dict(w)
                obj['id'] = wid
                items.append(obj)
        try:
            logger.debug("list_workflows in-memory items=%d", len(items))
        except Exception:
            pass
        return items

    if _FASTAPI_HEADERS:
        @app.post('/api/workflows')
        def create_workflow(body: dict, authorization: str = Header(None)):
            return create_workflow_impl(body, authorization)
    else:
        @app.post('/api/workflows')
        def create_workflow(body: dict, authorization: str = None):
            return create_workflow_impl(body, authorization)

    def create_workflow_impl(body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            # allow creating a default user like DummyClient does
            if _users:
                user_id = list(_users.keys())[0]
            else:
                raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400, detail='workspace not found')

        # basic validation similar to DummyClient and editor expectations
        def _validate_graph(graph):
            if graph is None:
                return None
            nodes = None
            if isinstance(graph, dict):
                nodes = graph.get('nodes')
            elif isinstance(graph, list):
                nodes = graph
            else:
                return ({'message': 'graph must be an object with "nodes" or an array of nodes'}, None)

            if nodes is None:
                return None

            errors = []
            for idx, el in enumerate(nodes):
                node_type = None
                cfg = None
                node_id = None
                if isinstance(el, dict) and 'data' in el:
                    data_field = el.get('data') or {}
                    label = (data_field.get('label') or '').lower()
                    cfg = data_field.get('config') or {}
                    node_id = el.get('id')
                    if 'http' in label:
                        node_type = 'http'
                    elif 'llm' in label or label.startswith('llm'):
                        node_type = 'llm'
                    elif 'webhook' in label:
                        node_type = 'webhook'
                    else:
                        node_type = label or None
                elif isinstance(el, dict) and el.get('type'):
                    node_type = el.get('type')
                    cfg = el
                    node_id = el.get('id')
                else:
                    errors.append(f'node at index {idx} has invalid shape')
                    continue

                if not node_id:
                    errors.append(f'node at index {idx} missing id')

                if node_type in ('http', 'http_request'):
                    url = None
                    if isinstance(cfg, dict):
                        url = cfg.get('url') or (cfg.get('config') or {}).get('url')
                    if not url:
                        errors.append(f'http node {node_id or idx} missing url')

                if node_type == 'slack' or (isinstance(node_type, str) and 'slack' in str(node_type).lower()):
                    url = None
                    if isinstance(cfg, dict):
                        url = cfg.get('url') or (cfg.get('config') or {}).get('url')
                    if not url:
                        errors.append(f'slack node {node_id or idx} missing url')

                if node_type == 'email' or (isinstance(node_type, str) and 'email' in str(node_type).lower()):
                    # require recipients and host at minimum
                    to_addrs = None
                    host = None
                    if isinstance(cfg, dict):
                        to_addrs = cfg.get('to') or cfg.get('recipients') or (cfg.get('config') or {}).get('to')
                        host = cfg.get('host') or (cfg.get('config') or {}).get('host')
                    if not to_addrs or not host:
                        errors.append(f'email node {node_id or idx} missing host or recipients')

                if node_type == 'llm':
                    prompt = None
                    if isinstance(cfg, dict):
                        prompt = cfg.get('prompt') if 'prompt' in cfg else (cfg.get('config') or {}).get('prompt')
                    if prompt is None:
                        errors.append(f'llm node {node_id or idx} missing prompt')

            if errors:
                first = errors[0]
                node_id = None
                try:
                    import re
                    m_idx = re.search(r'node at index (\d+)', first, re.I)
                    if m_idx:
                        idx = int(m_idx.group(1))
                        if isinstance(nodes, list) and 0 <= idx < len(nodes):
                            el = nodes[idx]
                            if isinstance(el, dict):
                                node_id = el.get('id')
                    else:
                        m_http = re.search(r'http node (\S+)', first, re.I)
                        m_llm = re.search(r'llm node (\S+)', first, re.I)
                        m_generic = m_http or m_llm
                        if m_generic:
                            gid = m_generic.group(1)
                            if gid.isdigit():
                                idx = int(gid)
                                if isinstance(nodes, list) and 0 <= idx < len(nodes):
                                    el = nodes[idx]
                                    if isinstance(el, dict):
                                        node_id = el.get('id')
                            else:
                                node_id = gid
                except Exception:
                    node_id = None

                return ({'message': first, 'node_id': node_id}, node_id)
            return None

        if 'graph' in body:
            g = body.get('graph')
            if g is not None and not isinstance(g, (dict, list)):
                msg = 'graph must be an object with "nodes" or an array of nodes'
                return JSONResponse(status_code=400, content={'detail': msg, 'message': msg})

        v = _validate_graph(body.get('graph'))
        if v is not None:
            detail = v[0]
            if isinstance(detail, dict):
                body_out = dict(detail)
                body_out['detail'] = detail
            else:
                body_out = {'message': str(detail), 'detail': detail}
                return JSONResponse(status_code=400, content=body_out)

        # Ensure we always have a non-null name when persisting to DB. The
        # frontend may omit a name for new workflows; derive a sensible default
        # from the graph (first node label) or fall back to a generic title.
        def _derive_workflow_name(payload: dict):
            if not isinstance(payload, dict):
                return 'Untitled Workflow'
            name_val = payload.get('name')
            if name_val:
                return name_val
            g = payload.get('graph')
            nodes = []
            if isinstance(g, dict):
                nodes = g.get('nodes') or []
            elif isinstance(g, list):
                nodes = g
            for n in nodes:
                if isinstance(n, dict):
                    data = n.get('data') or {}
                    label = data.get('label') or n.get('label') or None
                    if label:
                        try:
                            return str(label)
                        except Exception:
                            return 'Untitled Workflow'
            return 'Untitled Workflow'

        wf_name = _derive_workflow_name(body)

        # Run conservative canonicalization to preserve original configs
        try:
            from .node_schemas import canonicalize_graph
            body_graph = body.get('graph') if isinstance(body, dict) else None
            if body_graph is not None:
                body['graph'] = canonicalize_graph(body_graph)
        except Exception:
            pass

        # Soft server-side validation: collect warnings but do not fail by default
        try:
            from ._shared import _soft_validate_graph
            warnings = _soft_validate_graph(body.get('graph'))
        except Exception:
            warnings = []

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                wf = models.Workflow(workspace_id=wsid, name=wf_name, description=body.get('description'), graph=body.get('graph'))
                db.add(wf)
                db.commit()
                db.refresh(wf)
                out = {'id': wf.id, 'workspace_id': wf.workspace_id, 'name': wf.name}
                if warnings:
                    out['validation_warnings'] = warnings
                return out
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                return JSONResponse(status_code=500, content={'detail': 'failed to create workflow'})
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        wid = _next.get('workflow', 1)
        _next['workflow'] = wid + 1
        # Use derived name for in-memory store as well so behaviour matches DB
        _workflows[wid] = {'workspace_id': wsid, 'name': wf_name, 'description': body.get('description'), 'graph': body.get('graph')}
        out = {'id': wid, 'workspace_id': wsid, 'name': wf_name}
        if warnings:
            out['validation_warnings'] = warnings
        return out

    if _FASTAPI_HEADERS:
        @app.put('/api/workflows/{wid}')
        def update_workflow(wid: int, body: dict, authorization: str = Header(None)):
            return update_workflow_impl(wid, body, authorization)
    else:
        @app.put('/api/workflows/{wid}')
        def update_workflow(wid: int, body: dict, authorization: str = None):
            return update_workflow_impl(wid, body, authorization)

    def update_workflow_impl(wid: int, body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)

        # preserve original config and canonicalize incoming graph
        try:
            from .node_schemas import canonicalize_graph
            if 'graph' in body and body.get('graph') is not None:
                body['graph'] = canonicalize_graph(body.get('graph'))
        except Exception:
            pass

        # Soft validation warnings for updates
        try:
            from ._shared import _soft_validate_graph
            warnings = _soft_validate_graph(body.get('graph'))
        except Exception:
            warnings = []

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                wf = db.query(models.Workflow).filter(models.Workflow.id == wid).first()
                if not wf or wf.workspace_id != wsid:
                    raise HTTPException(status_code=404)
                if 'name' in body:
                    wf.name = body.get('name')
                if 'description' in body:
                    wf.description = body.get('description')
                if 'graph' in body:
                    wf.graph = body.get('graph')
                db.add(wf)
                db.commit()
                out = {'id': wf.id, 'workspace_id': wf.workspace_id, 'name': wf.name}
                if warnings:
                    out['validation_warnings'] = warnings
                return out
            except HTTPException:
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

        wf = _workflows.get(wid)
        if not wf or wf.get('workspace_id') != wsid:
            raise HTTPException(status_code=404)
        if 'name' in body:
            wf['name'] = body.get('name')
        if 'description' in body:
            wf['description'] = body.get('description')
        if 'graph' in body:
            wf['graph'] = body.get('graph')
        out = {'id': wid, 'workspace_id': wf.get('workspace_id'), 'name': wf.get('name')}
        if warnings:
            out['validation_warnings'] = warnings
        return out

    # Webhooks: create/list/delete per-workflow and public trigger
    if _FASTAPI_HEADERS:
        @app.post('/api/workflows/{wf_id}/webhooks')
        def create_webhook(wf_id: int, body: dict, authorization: str = Header(None)):
            return create_webhook_impl(wf_id, body, authorization)
    else:
        @app.post('/api/workflows/{wf_id}/webhooks')
        def create_webhook(wf_id: int, body: dict, authorization: str = None):
            return create_webhook_impl(wf_id, body, authorization)

    def create_webhook_impl(wf_id: int, body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)

        # ensure workflow exists and belongs to workspace
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                wf = db.query(models.Workflow).filter(models.Workflow.id == wf_id).first()
                if not wf or wf.workspace_id != wsid:
                    return {'detail': 'workflow not found'}
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        else:
            wf = _workflows.get(wf_id)
            if not wf or wf.get('workspace_id') != wsid:
                raise HTTPException(status_code=400, detail='workflow not found in workspace')

        hid = _next.get('webhook', 1)
        _next['webhook'] = hid + 1
        path_val = body.get('path') or f"{wf_id}-{hid}"
        _webhooks[hid] = {'workflow_id': wf_id, 'path': path_val, 'description': body.get('description'), 'workspace_id': wsid}
        return {'id': hid, 'path': path_val, 'workflow_id': wf_id}

    @app.get('/api/workflows/{wf_id}/webhooks')
    def list_webhooks(wf_id: int):
        out = []
        for hid, h in _webhooks.items():
            if h.get('workflow_id') == wf_id:
                out.append({'id': hid, 'path': h.get('path'), 'description': h.get('description'), 'created_at': None})
        return out

    if _FASTAPI_HEADERS:
        @app.delete('/api/workflows/{wf_id}/webhooks/{hid}')
        def delete_webhook(wf_id: int, hid: int, authorization: str = Header(None)):
            return delete_webhook_impl(wf_id, hid, authorization)
    else:
        @app.delete('/api/workflows/{wf_id}/webhooks/{hid}')
        def delete_webhook(wf_id: int, hid: int, authorization: str = None):
            return delete_webhook_impl(wf_id, hid, authorization)

    def delete_webhook_impl(wf_id: int, hid: int, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        row = _webhooks.get(hid)
        if not row or row.get('workflow_id') != wf_id:
            raise HTTPException(status_code=404)
        del _webhooks[hid]
        return {'status': 'deleted'}

    if _FASTAPI_HEADERS:
        @app.post('/api/webhook/{workflow_id}/{trigger_id}')
        def public_webhook_trigger(workflow_id: int, trigger_id: str, body: dict, authorization: str = Header(None)):
            return public_webhook_trigger_impl(workflow_id, trigger_id, body, authorization)
    else:
        @app.post('/api/webhook/{workflow_id}/{trigger_id}')
        def public_webhook_trigger(workflow_id: int, trigger_id: str, body: dict, authorization: str = None):
            return public_webhook_trigger_impl(workflow_id, trigger_id, body, authorization)

    def public_webhook_trigger_impl(workflow_id: int, trigger_id: str, body: dict, authorization: str = None):
        # Create a run and return queued status. This route intentionally allows
        # unauthenticated calls (public trigger) but will create an audit entry
        # if workspace/user can be determined.
        run_id = _next.get('run', 1)
        _next['run'] = run_id + 1
        _runs = ctx.get('_runs')
        _runs[run_id] = {'workflow_id': workflow_id, 'status': 'queued'}
        # try to attach workspace and user when possible
        user_id = None
        try:
            user_id = ctx.get('_user_from_token')(authorization)
        except Exception:
            user_id = None
        wsid = None
        try:
            wsid = _workflows.get(workflow_id, {}).get('workspace_id')
        except Exception:
            wsid = None
        try:
            _add_audit(wsid, user_id, 'create_run', object_type='run', object_id=run_id, detail='trigger')
        except Exception:
            pass
        return {'run_id': run_id, 'status': 'queued'}

    # Test connection: POST /api/providers/{id}/test_connection
    if _FASTAPI_HEADERS:
        @app.post('/api/providers/{pid}/test_connection')
        def test_provider_connection(pid: int, body: dict = None, authorization: str = Header(None)):
            return test_provider_connection_impl(pid, body or {}, authorization)
    else:
        @app.post('/api/providers/{pid}/test_connection')
        def test_provider_connection(pid: int, body: dict = None, authorization: str = None):
            return test_provider_connection_impl(pid, body or {}, authorization)

    def test_provider_connection_impl(pid: int, body: dict = None, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization) if authorization is not None else None
        # allow unauthenticated in some client flows, but fail if we can't resolve a workspace
        if not user_id:
            if _users:
                user_id = list(_users.keys())[0]
            else:
                raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)

        # body may contain an inline secret object to override stored secret
        inline_secret = body.get('secret') if isinstance(body, dict) else None

        # resolve provider
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                p = db.query(models.Provider).filter(models.Provider.id == pid).first()
                if not p or p.workspace_id != wsid:
                    raise HTTPException(status_code=404)
                secret_record = None
                if inline_secret is not None:
                    # create ephemeral secret (not persisted) to test connection
                    try:
                        import json as _json
                        secret_value = _json.dumps(inline_secret)
                    except Exception:
                        return JSONResponse(status_code=400, content={'detail': 'invalid secret payload'})
                    # decrypt/encrypt not needed for ephemeral; pass plaintext to adapter
                    secret_record = {'value': secret_value}
                elif getattr(p, 'secret_id', None):
                    s = db.query(models.Secret).filter(models.Secret.id == p.secret_id).first()
                    if not s:
                        raise HTTPException(status_code=400, detail='secret not found')
                    # decrypt when possible
                    sec_val = getattr(s, 'encrypted_value', None)
                    try:
                        if decrypt_value is not None:
                            sec_val = decrypt_value(sec_val)
                    except Exception:
                        pass
                    secret_record = {'value': sec_val}
                # attempt provider-specific test using adapters in tasks or adapters modules
                test_ok = False
                test_err = None
                try:
                    # simplistic tests for known types
                    if p.type == 's3':
                        import boto3
                        import botocore
                        import json as _json
                        creds = _json.loads(secret_record.get('value')) if isinstance(secret_record.get('value'), str) else secret_record.get('value')
                        session = boto3.session.Session(aws_access_key_id=creds.get('access_key'), aws_secret_access_key=creds.get('secret_key'), aws_session_token=creds.get('session_token'))
                        s3 = session.client('s3')
                        s3.list_buckets()
                        test_ok = True
                    elif p.type == 'smtp':
                        import smtplib
                        import json as _json
                        creds = _json.loads(secret_record.get('value')) if isinstance(secret_record.get('value'), str) else secret_record.get('value')
                        host = creds.get('host')
                        port = int(creds.get('port') or 25)
                        server = smtplib.SMTP(host, port, timeout=5)
                        server.noop()
                        server.quit()
                        test_ok = True
                    else:
                        # default: succeed if a secret exists
                        if secret_record is not None:
                            test_ok = True
                        else:
                            test_ok = False
                except Exception as e:
                    test_ok = False
                    test_err = str(e)

                # update provider last_tested metadata
                try:
                    p.last_tested_at = _dt.utcnow()
                    p.last_tested_by = user_id
                    db.add(p)
                    db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                # audit
                try:
                    _add_audit(wsid, user_id, 'test_provider', object_type='provider', object_id=pid, detail=p.type)
                except Exception:
                    pass

                if test_ok:
                    return {'ok': True}
                return JSONResponse(status_code=400, content={'ok': False, 'error': 'test failed', 'detail': test_err})
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        else:
            p = _providers.get(pid)
            if not p or p.get('workspace_id') != wsid:
                raise HTTPException(status_code=404)
            # in-memory: basic check
            if inline_secret or p.get('secret_id'):
                # record last_tested_at in-memory
                p['last_tested_at'] = _dt.utcnow()
                try:
                    _add_audit(wsid, user_id, 'test_provider', object_type='provider', object_id=pid, detail=p.get('type'))
                except Exception:
                    pass
                return {'ok': True}
            return JSONResponse(status_code=400, content={'ok': False, 'error': 'no secret configured'})

    # Audit logs: list and export (CSV)
    if _FASTAPI_HEADERS:
        @app.get('/api/audit_logs')
        def list_audit_logs(limit: int = 50, offset: int = 0, action: str = None, object_type: str = None, user_id: int = None, date_from: str = None, date_to: str = None, authorization: str = Header(None)):
            return list_audit_logs_impl(limit, offset, action, object_type, user_id, date_from, date_to, authorization)
    else:
        @app.get('/api/audit_logs')
        def list_audit_logs(limit: int = 50, offset: int = 0, action: str = None, object_type: str = None, user_id: int = None, date_from: str = None, date_to: str = None, authorization: str = None):
            return list_audit_logs_impl(limit, offset, action, object_type, user_id, date_from, date_to, authorization)

    def list_audit_logs_impl(limit: int = 50, offset: int = 0, action: str = None, object_type: str = None, user_id: int = None, date_from: str = None, date_to: str = None, authorization: str = None):
        # require authenticated user
        uid = ctx.get('_user_from_token')(authorization)
        if not uid:
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(uid)
        if not wsid:
            return {'items': [], 'total': 0, 'limit': limit, 'offset': offset}

        items = []
        total = 0
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                q = db.query(models.AuditLog).filter(models.AuditLog.workspace_id == wsid)
                if action:
                    q = q.filter(models.AuditLog.action == action)
                if object_type:
                    q = q.filter(models.AuditLog.object_type == object_type)
                if user_id:
                    q = q.filter(models.AuditLog.user_id == user_id)
                # date filters (assume ISO dates)
                try:
                    from datetime import datetime as _dt
                    if date_from:
                        df = _dt.fromisoformat(date_from)
                        q = q.filter(models.AuditLog.timestamp >= df)
                    if date_to:
                        dt = _dt.fromisoformat(date_to)
                        q = q.filter(models.AuditLog.timestamp <= dt)
                except Exception:
                    pass
                total = q.count()
                rows = q.order_by(models.AuditLog.id.desc()).offset(offset).limit(limit).all()
                out = []
                for r in rows:
                    out.append({'id': r.id, 'workspace_id': r.workspace_id, 'user_id': r.user_id, 'action': r.action, 'object_type': r.object_type, 'object_id': r.object_id, 'detail': r.detail, 'timestamp': getattr(r, 'timestamp', None)})
                items = out
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        else:
            # no DB: best-effort if ctx provided a simple in-memory list (not normally present)
            _audit_store = ctx.get('_audit_logs')
            if _audit_store and isinstance(_audit_store, list):
                filtered = [a for a in _audit_store if a.get('workspace_id') == wsid]
                if action:
                    filtered = [a for a in filtered if a.get('action') == action]
                if object_type:
                    filtered = [a for a in filtered if a.get('object_type') == object_type]
                if user_id:
                    filtered = [a for a in filtered if a.get('user_id') == user_id]
                total = len(filtered)
                items = filtered[offset: offset + limit]

        return {'items': items, 'total': total, 'limit': limit, 'offset': offset}

    if _FASTAPI_HEADERS:
        @app.get('/api/audit_logs/export')
        def export_audit_logs(action: str = None, object_type: str = None, user_id: int = None, date_from: str = None, date_to: str = None, authorization: str = Header(None)):
            return export_audit_logs_impl(action, object_type, user_id, date_from, date_to, authorization)
    else:
        @app.get('/api/audit_logs/export')
        def export_audit_logs(action: str = None, object_type: str = None, user_id: int = None, date_from: str = None, date_to: str = None, authorization: str = None):
            return export_audit_logs_impl(action, object_type, user_id, date_from, date_to, authorization)

    def export_audit_logs_impl(action: str = None, object_type: str = None, user_id: int = None, date_from: str = None, date_to: str = None, authorization: str = None):
        uid = ctx.get('_user_from_token')(authorization)
        if not uid:
            raise HTTPException(status_code=401)

        # role check (admin required)
        is_admin = False
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                u = db.query(models.User).filter(models.User.id == uid).first()
                if u and getattr(u, 'role', '') == 'admin':
                    is_admin = True
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        else:
            # fallback: check in-memory users if provided
            _users_local = ctx.get('_users') or {}
            u = _users_local.get(uid)
            if u and u.get('role') == 'admin':
                is_admin = True

        if not is_admin:
            raise HTTPException(status_code=403)

        # reuse listing logic to get items for this admin's workspace
        wsid = _workspace_for_user(uid)
        if not wsid:
            return ''

        rows = []
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                q = db.query(models.AuditLog).filter(models.AuditLog.workspace_id == wsid)
                if action:
                    q = q.filter(models.AuditLog.action == action)
                if object_type:
                    q = q.filter(models.AuditLog.object_type == object_type)
                if user_id:
                    q = q.filter(models.AuditLog.user_id == user_id)
                try:
                    from datetime import datetime as _dt
                    if date_from:
                        df = _dt.fromisoformat(date_from)
                        q = q.filter(models.AuditLog.timestamp >= df)
                    if date_to:
                        dt = _dt.fromisoformat(date_to)
                        q = q.filter(models.AuditLog.timestamp <= dt)
                except Exception:
                    pass
                rows = q.order_by(models.AuditLog.id.desc()).all()
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        else:
            _audit_store = ctx.get('_audit_logs') or []
            rows = [a for a in _audit_store if a.get('workspace_id') == wsid]
            if action:
                rows = [a for a in rows if a.get('action') == action]
            if object_type:
                rows = [a for a in rows if a.get('object_type') == object_type]
            if user_id:
                rows = [a for a in rows if a.get('user_id') == user_id]

        # build CSV
        try:
            import csv, io
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(['id', 'workspace_id', 'user_id', 'action', 'object_type', 'object_id', 'detail', 'timestamp'])
            for r in rows:
                if _DB_AVAILABLE:
                    writer.writerow([r.id, r.workspace_id, r.user_id, r.action, r.object_type or '', r.object_id or '', r.detail or '', getattr(r, 'timestamp', '') or ''])
                else:
                    writer.writerow([r.get('id'), r.get('workspace_id'), r.get('user_id'), r.get('action'), r.get('object_type') or '', r.get('object_id') or '', r.get('detail') or '', r.get('timestamp') or ''])
            return buf.getvalue()
        except Exception:
            return ''