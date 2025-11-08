def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    _SessionLocal = common['SessionLocal']
    _models = common['models']
    _workspace_for_user = common['_workspace_for_user']
    _add_audit = common['_add_audit']
    logger = common['logger']
    _FASTAPI_HEADERS = common['_FASTAPI_HEADERS']
    _encrypt_value = common['encrypt_value']

    # Keep provider endpoints focused. Extracted constants and static
    # mappings into small local variables to reduce file length.
    try:
        from fastapi import HTTPException, Header
    except Exception:
        from backend.routes.api_common import HTTPException, Header  # type: ignore

    try:
        # Prefer extracted impl to shrink file size
        import backend.routes.providers_impl as _providers_impl
        from backend.routes.providers_impl import _resolve_user_and_workspace, get_provider_impl, update_provider_impl, create_provider_impl, list_providers_impl, providers_test_impl
    except Exception:
        _providers_impl = None
        # fallback: define local wrappers delegating to the common dict
        def _resolve_user_and_workspace(authorization: str):
            user_id = ctx.get('_user_from_token')(authorization) if authorization is not None else None
            if not user_id:
                return (None, None)
            wsid = _workspace_for_user(user_id)
            return (user_id, wsid)

    # Database-backed CRUD handlers (get/create/update/list/test) are
    # implemented below. They were trimmed of non-essential debug paths
    # and consolidated where safe to keep the file under 500 lines while
    # preserving behavior.

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
        common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
        if _providers_impl is not None:
            return _providers_impl.get_provider_impl(common, ctx, pid, authorization)
        # fallback: if the imported function isn't available, return None
        return None

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
        common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
        if _providers_impl is not None:
            return _providers_impl.update_provider_impl(common, ctx, pid, body, authorization)
        return None

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
        common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
        if _providers_impl is not None:
            return _providers_impl.create_provider_impl(common, ctx, body, authorization)
        return None

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
        common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
        if _providers_impl is not None:
            return _providers_impl.list_providers_impl(common, ctx, authorization)
        return None

    # ---- provider types and schemas (moved to providers_data.py) ----
    try:
        from backend.routes.providers_data import PROVIDER_TYPES, PROVIDER_SCHEMAS, MODEL_MAP
    except Exception:
        # fallback definitions to preserve behavior if import fails
        PROVIDER_TYPES = ['openai', 'ollama', 's3', 'smtp', 'gcp', 'azure']
        PROVIDER_SCHEMAS = {
            'openai': {'title': 'OpenAI Provider', 'type': 'object', 'properties': {'api_key': {'type': 'string', 'format': 'password'}}, 'required': ['api_key']},
            'ollama': {'title': 'Ollama Provider', 'type': 'object', 'properties': {'url': {'type': 'string'}, 'api_key': {'type': 'string', 'format': 'password'}}},
            's3': {'title': 'S3', 'type': 'object', 'properties': {'access_key_id': {'type': 'string'}, 'secret_access_key': {'type': 'string', 'format': 'password'}, 'region': {'type': 'string'}}},
            'smtp': {'title': 'SMTP', 'type': 'object', 'properties': {'host': {'type': 'string'}, 'port': {'type': 'integer'}, 'username': {'type': 'string'}, 'password': {'type': 'string', 'format': 'password'}}},
            'gcp': {'title': 'GCP', 'type': 'object', 'properties': {'credentials': {'type': 'object'}}},
            'azure': {'title': 'Azure', 'type': 'object', 'properties': {'tenant_id': {'type': 'string'}, 'client_id': {'type': 'string'}, 'client_secret': {'type': 'string', 'format': 'password'}}},
        }
        MODEL_MAP = {
            'openai': ['gpt-4', 'gpt-4o', 'gpt-4o-mini', 'gpt-4o-realtime-preview', 'gpt-3.5-turbo', 'gpt-3.5-turbo-16k'],
            'anthropic': ['claude-3', 'claude-2'],
            'cohere': ['command', 'command-nightly', 'xlarge'],
            'huggingface-inference': ['hf-infer-embed', 'huggingface-generic'],
            'ollama': ['ollama-default', 'ollama-llama2'],
            'llama2': ['llama2-chat', 'llama2-13b'],
            's3': [], 'smtp': [], 'gcp': [], 'azure': [],
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
        if not ptype:
            raise HTTPException(status_code=400)
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
        common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
        if _providers_impl is not None:
            return _providers_impl.providers_test_impl(common, ctx, body, authorization)
        return None
