def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    SessionLocal = common['SessionLocal']
    models = common['models']
    _workspace_for_user = common['_workspace_for_user']
    _add_audit = common['_add_audit']
    logger = common['logger']
    _FASTAPI_HEADERS = common['_FASTAPI_HEADERS']
    encrypt_value = common['encrypt_value']

    # Ensure console logging is available for easier debugging in development
    try:
        import logging, sys

        def _ensure_console_handler(log):
            try:
                if not getattr(log, '_console_handler_added', False):
                    ch = logging.StreamHandler(sys.stdout)
                    ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
                    ch.setLevel(logging.DEBUG)
                    log.addHandler(ch)
                    setattr(log, '_console_handler_added', True)
            except Exception:
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
            root = logging.getLogger()
            _ensure_console_handler(root)
        except Exception:
            pass

        try:
            logger.setLevel(logging.DEBUG)
            logging.getLogger().setLevel(logging.DEBUG)
        except Exception:
            pass
    except Exception:
        pass

    try:
        from fastapi import HTTPException, Header
        from fastapi.responses import JSONResponse
        from typing import List
        from backend.schemas import ProviderCreate, ProviderOut
    except Exception:
        from backend.routes.api_common import HTTPException, Header, JSONResponse  # type: ignore
        ProviderCreate = None
        ProviderOut = None

    # ---- helper: resolve user and workspace (DB-only) ----
    def _resolve_user_and_workspace(authorization: str):
        user_id = ctx.get('_user_from_token')(authorization) if authorization is not None else None
        if not user_id:
            return (None, None)
        wsid = _workspace_for_user(user_id)
        # if workspace missing, create it in DB (preserve previous auto-create behavior)
        if not wsid and SessionLocal is not None and models is not None:
            try:
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
                        logger.info("providers: created workspace %s for user %s", wsid, user_id)
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
        return (user_id, wsid)

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
        user_id, wsid = _resolve_user_and_workspace(authorization)
        try:
            logger.debug("get_provider called pid=%r resolved_user=%r workspace=%r", pid, user_id, wsid)
        except Exception:
            pass
        if not user_id:
            raise HTTPException(status_code=401)
        if not wsid:
            raise HTTPException(status_code=400)
        if SessionLocal is None or models is None:
            raise HTTPException(status_code=500, detail='database unavailable')
        db = None
        try:
            db = SessionLocal()
            p = db.query(models.Provider).filter(models.Provider.id == pid).first()
            if not p or p.workspace_id != wsid:
                try:
                    logger.debug("get_provider: provider not found or wrong workspace pid=%r", pid)
                except Exception:
                    pass
                raise HTTPException(status_code=404)
            # Do not return provider config or any sensitive fields
            out = {'id': p.id, 'workspace_id': p.workspace_id, 'type': p.type, 'secret_id': getattr(p, 'secret_id', None), 'last_tested_at': getattr(p, 'last_tested_at', None)}
            try:
                logger.info("get_provider: returning provider id=%s workspace=%s type=%s", p.id, p.workspace_id, p.type)
            except Exception:
                pass
            return out
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass

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
        user_id, wsid = _resolve_user_and_workspace(authorization)
        try:
            logger.debug("update_provider called pid=%r body_keys=%r resolved_user=%r workspace=%r", pid, list(body.keys()) if isinstance(body, dict) else None, user_id, wsid)
        except Exception:
            pass
        if not user_id:
            raise HTTPException(status_code=401)
        if not wsid:
            raise HTTPException(status_code=400)
        if SessionLocal is None or models is None:
            return JSONResponse(status_code=500, content={'detail': 'database unavailable'})

        inline_secret = body.get('secret') if isinstance(body, dict) else None
        secret_id = body.get('secret_id') if isinstance(body, dict) else None

        # create inline secret as DB Secret record
        if inline_secret is not None:
            try:
                import json as _json
                secret_value = _json.dumps(inline_secret)
            except Exception:
                return JSONResponse(status_code=400, content={'detail': 'invalid secret payload'})
            db = None
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
                try:
                    logger.info("update_provider: created secret id=%s for workspace=%s (provider update)", secret_id, wsid)
                except Exception:
                    pass
            except Exception:
                try:
                    if db:
                        db.rollback()
                except Exception:
                    pass
                return JSONResponse(status_code=500, content={'detail': 'failed to create secret'})
            finally:
                try:
                    if db:
                        db.close()
                except Exception:
                    pass

        # validate secret belongs to workspace
        if secret_id is not None:
            db = None
            try:
                db = SessionLocal()
                s = db.query(models.Secret).filter(models.Secret.id == secret_id, models.Secret.workspace_id == wsid).first()
                if not s:
                    return JSONResponse(status_code=400, content={'detail': 'secret_id not found in workspace'})
            finally:
                try:
                    if db:
                        db.close()
                except Exception:
                    pass

        # update provider
        db = None
        try:
            db = SessionLocal()
            p = db.query(models.Provider).filter(models.Provider.id == pid).first()
            if not p or p.workspace_id != wsid:
                try:
                    logger.debug("update_provider: provider not found or wrong workspace pid=%r", pid)
                except Exception:
                    pass
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
            try:
                logger.info("update_provider: updated provider id=%s workspace=%s type=%s", p.id, p.workspace_id, p.type)
            except Exception:
                pass
            return {'id': p.id, 'workspace_id': p.workspace_id, 'type': p.type, 'secret_id': getattr(p, 'secret_id', None), 'last_tested_at': getattr(p, 'last_tested_at', None)}
        except HTTPException:
            raise
        except Exception:
            try:
                if db:
                    db.rollback()
            except Exception:
                pass
            return JSONResponse(status_code=500, content={'detail': 'failed to update provider'})
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass

    # provider create
    if _FASTAPI_HEADERS:
        @app.post('/api/providers')
        def create_provider(body: dict, authorization: str = Header(None)):
            return create_provider_impl(body, authorization)
    else:
        @app.post('/api/providers')
        def create_provider(body: dict, authorization: str = None):
            return create_provider_impl(body, authorization)

    def create_provider_impl(body: dict, authorization: str = None):
        user_id, wsid = _resolve_user_and_workspace(authorization)
        try:
            logger.debug("create_provider called body_keys=%r resolved_user=%r workspace=%r", list(body.keys()) if isinstance(body, dict) else None, user_id, wsid)
        except Exception:
            pass
        if not user_id:
            raise HTTPException(status_code=401)
        if not wsid:
            raise HTTPException(status_code=400)
        if SessionLocal is None or models is None:
            return JSONResponse(status_code=500, content={'detail': 'database unavailable'})

        secret_id = body.get('secret_id') if isinstance(body, dict) else None
        inline_secret = body.get('secret') if isinstance(body, dict) else None

        if inline_secret is not None:
            try:
                import json as _json
                secret_value = _json.dumps(inline_secret)
            except Exception:
                return JSONResponse(status_code=400, content={'detail': 'invalid secret payload'})
            db = None
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
                    if db:
                        db.rollback()
                except Exception:
                    pass
                return JSONResponse(status_code=500, content={'detail': 'failed to create secret'})
            finally:
                try:
                    if db:
                        db.close()
                except Exception:
                    pass

        if secret_id is not None:
            db = None
            try:
                db = SessionLocal()
                s = db.query(models.Secret).filter(models.Secret.id == secret_id, models.Secret.workspace_id == wsid).first()
                if not s:
                    raise HTTPException(status_code=400, detail='secret_id not found in workspace')
            finally:
                try:
                    if db:
                        db.close()
                except Exception:
                    pass

        db = None
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
            try:
                logger.info("create_provider: created provider id=%s workspace=%s type=%s secret_id=%s", p.id, p.workspace_id, p.type, getattr(p, 'secret_id', None))
            except Exception:
                pass
            # Do not return provider config or secret material
            return {'id': p.id, 'workspace_id': p.workspace_id, 'type': p.type, 'secret_id': p.secret_id}
        except Exception:
            try:
                if db:
                    db.rollback()
            except Exception:
                pass
            return JSONResponse(status_code=500, content={'detail': 'failed to create provider'})
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass

    # list providers
    if _FASTAPI_HEADERS:
        @app.get('/api/providers')
        def list_providers(authorization: str = Header(None)):
            return list_providers_impl(authorization)
    else:
        @app.get('/api/providers')
        def list_providers(authorization: str = None):
            return list_providers_impl(authorization)

    def list_providers_impl(authorization: str = None):
        user_id, wsid = _resolve_user_and_workspace(authorization)
        try:
            logger.debug("list_providers called authorization=%r resolved_user=%r workspace=%r", authorization, user_id, wsid)
        except Exception:
            pass
        if not user_id:
            raise HTTPException(status_code=401)
        if not wsid:
            return []
        if SessionLocal is None or models is None:
            raise HTTPException(status_code=500, detail='database unavailable')
        db = None
        try:
            db = SessionLocal()
            rows = db.query(models.Provider).filter(models.Provider.workspace_id == wsid).all()
            try:
                logger.debug("list_providers DB rows=%d workspace=%s", len(rows), wsid)
            except Exception:
                pass
            out = []
            for r in rows:
                out.append({'id': r.id, 'workspace_id': r.workspace_id, 'type': r.type, 'secret_id': getattr(r, 'secret_id', None), 'last_tested_at': getattr(r, 'last_tested_at', None)})
            try:
                logger.info("list_providers: returning %d providers for workspace=%s (DB)", len(out), wsid)
            except Exception:
                pass
            return out
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass

    # ---- provider types and schemas ----
    PROVIDER_TYPES = ['openai', 'ollama', 's3', 'smtp', 'gcp', 'azure']
    PROVIDER_SCHEMAS = {
        'openai': {
            'title': 'OpenAI Provider',
            'type': 'object',
            'properties': {
                'api_key': {'type': 'string', 'format': 'password'}
            },
            'required': ['api_key']
        },
        'ollama': {
            'title': 'Ollama Provider',
            'type': 'object',
            'properties': {
                'url': {'type': 'string'},
                'api_key': {'type': 'string', 'format': 'password'}
            }
        },
        's3': {
            'title': 'S3',
            'type': 'object',
            'properties': {
                'access_key_id': {'type': 'string'},
                'secret_access_key': {'type': 'string', 'format': 'password'},
                'region': {'type': 'string'}
            }
        },
        'smtp': {
            'title': 'SMTP',
            'type': 'object',
            'properties': {
                'host': {'type': 'string'},
                'port': {'type': 'integer'},
                'username': {'type': 'string'},
                'password': {'type': 'string', 'format': 'password'}
            }
        },
        'gcp': {'title': 'GCP', 'type': 'object', 'properties': {'credentials': {'type': 'object'}}},
        'azure': {'title': 'Azure', 'type': 'object', 'properties': {'tenant_id': {'type': 'string'}, 'client_id': {'type': 'string'}, 'client_secret': {'type': 'string', 'format': 'password'}}}
    }

    if _FASTAPI_HEADERS:
        @app.get('/api/provider_types')
        def provider_types(authorization: str = Header(None)):
            return provider_types_impl(authorization)
    else:
        @app.get('/api/provider_types')
        def provider_types(authorization: str = None):
            return provider_types_impl(authorization)

    def provider_types_impl(authorization: str = None):
        # allow unauthenticated access to types list but still log resolved user for debugging
        user_id = ctx.get('_user_from_token')(authorization)
        try:
            logger.debug("provider_types called authorization=%r resolved_user=%r", authorization, user_id)
        except Exception:
            pass
        try:
            logger.info("provider_types: returning %d types", len(PROVIDER_TYPES))
        except Exception:
            pass
        return PROVIDER_TYPES

    if _FASTAPI_HEADERS:
        @app.get('/api/provider_schema/{ptype}')
        def provider_schema(ptype: str, authorization: str = Header(None)):
            return provider_schema_impl(ptype, authorization)
    else:
        @app.get('/api/provider_schema/{ptype}')
        def provider_schema(ptype: str, authorization: str = None):
            return provider_schema_impl(ptype, authorization)

    def provider_schema_impl(ptype: str, authorization: str = None):
        # simple schema lookup; return 404 if unknown type to let frontend fallback
        if not ptype:
            raise HTTPException(status_code=400)
        schema = PROVIDER_SCHEMAS.get(ptype)
        if not schema:
            try:
                logger.debug("provider_schema: unknown type=%s", ptype)
            except Exception:
                pass
            raise HTTPException(status_code=404)
        try:
            logger.debug("provider_schema: returning schema for type=%s", ptype)
        except Exception:
            pass
        return schema

    # provider models endpoint - lightweight list of known model identifiers per provider type
    if _FASTAPI_HEADERS:
        @app.get('/api/provider_models/{ptype}')
        def provider_models(ptype: str, authorization: str = Header(None)):
            return provider_models_impl(ptype, authorization)
    else:
        @app.get('/api/provider_models/{ptype}')
        def provider_models(ptype: str, authorization: str = None):
            return provider_models_impl(ptype, authorization)

    def provider_models_impl(ptype: str, authorization: str = None):
        # Return a conservative list of model identifiers for supported provider types.
        # Unknown types return 404 so the frontend can fallback gracefully.
        if not ptype:
            raise HTTPException(status_code=400)
        # Conservative, easy-to-maintain static mapping of provider types ->
        # example model identifiers to surface as useful defaults in the UI.
        # Note: many providers (Azure, self-hosted adapters, Hugging Face) use
        # workspace- or customer-specific deployment names. These lists are
        # intentionally generic and informational; they can be replaced with a
        # dynamic, workspace-aware service later if desired.
        MODEL_MAP = {
            'openai': [
                'gpt-4',
                'gpt-4o',
                'gpt-4o-mini',
                'gpt-4o-realtime-preview',
                'gpt-3.5-turbo',
                'gpt-3.5-turbo-16k'
            ],
            'anthropic': [
                'claude-3',
                'claude-2'
            ],
            'cohere': [
                'command',
                'command-nightly',
                'xlarge'
            ],
            'huggingface-inference': [
                'hf-infer-embed',
                'huggingface-generic'
            ],
            'ollama': [
                'ollama-default',
                'ollama-llama2'
            ],
            # Generic self-hosted / Llama2 identifiers (names vary by deploy).
            'llama2': [
                'llama2-chat',
                'llama2-13b'
            ],
            # Other types don't have canonical model names here. Azure often
            # uses per-workspace deployments so return an empty list.
            's3': [],
            'smtp': [],
            'gcp': [],
            'azure': []
        }
        models = MODEL_MAP.get(ptype)
        if models is None:
            try:
                logger.debug("provider_models: unknown type=%s", ptype)
            except Exception:
                pass
            raise HTTPException(status_code=404)
        try:
            logger.debug("provider_models: returning %d models for type=%s", len(models), ptype)
        except Exception:
            pass
        return models

    # provider test endpoint - lightweight validation that required creds/secret exists
    if _FASTAPI_HEADERS:
        @app.post('/api/providers/test')
        def providers_test(body: dict, authorization: str = Header(None)):
            return providers_test_impl(body, authorization)
    else:
        @app.post('/api/providers/test')
        def providers_test(body: dict, authorization: str = None):
            return providers_test_impl(body, authorization)

    def providers_test_impl(body: dict, authorization: str = None):
        user_id, wsid = _resolve_user_and_workspace(authorization)
        try:
            logger.debug("providers_test called body_keys=%r resolved_user=%r workspace=%r", list(body.keys()) if isinstance(body, dict) else None, user_id, wsid)
        except Exception:
            pass
        if not user_id:
            raise HTTPException(status_code=401)
        if not wsid:
            raise HTTPException(status_code=400)
        ptype = body.get('type') if isinstance(body, dict) else None
        if not ptype:
            return JSONResponse(status_code=400, content={'detail': 'type required'})
        # Ensure either inline secret or secret_id present
        inline_secret = body.get('secret') if isinstance(body, dict) else None
        secret_id = body.get('secret_id') if isinstance(body, dict) else None
        if inline_secret is None and not secret_id:
            return JSONResponse(status_code=400, content={'detail': 'secret or secret_id required'})
        # if secret_id validate workspace
        if secret_id is not None:
            if SessionLocal is None or models is None:
                return JSONResponse(status_code=500, content={'detail': 'database unavailable'})
            db = None
            try:
                db = SessionLocal()
                s = db.query(models.Secret).filter(models.Secret.id == secret_id).first()
                if not s or s.workspace_id != wsid:
                    try:
                        logger.debug("providers_test: secret_id=%s not found in workspace=%s", secret_id, wsid)
                    except Exception:
                        pass
                    return JSONResponse(status_code=400, content={'detail': 'secret_id not found in workspace'})
            finally:
                try:
                    if db:
                        db.close()
                except Exception:
                    pass
        # Lightweight success response. Detailed provider-specific live checks are performed in adapters when running nodes.
        try:
            logger.info("providers.test type=%s workspace=%s user=%s", ptype, wsid, user_id)
        except Exception:
            pass
        return {'ok': True}
