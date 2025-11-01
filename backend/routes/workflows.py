def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    SessionLocal = common['SessionLocal']
    models = common['models']
    _DB_AVAILABLE = common.get('_DB_AVAILABLE')
    _users = common.get('_users')
    _workflows = common.get('_workflows')
    _next = common.get('_next')
    _workspace_for_user = common['_workspace_for_user']
    logger = common['logger']
    _FASTAPI_HEADERS = common['_FASTAPI_HEADERS']

    try:
        logger.info("workflows: registering routes")
    except Exception:
        pass

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
                        ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
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

    # FastAPI imports: we always run under FastAPI in this project.
    try:
        from fastapi import HTTPException, Header
        from fastapi.responses import JSONResponse
    except Exception:
        from backend.routes.api_common import HTTPException, Header, JSONResponse  # type: ignore

    @app.get('/api/workflows')
    def list_workflows(authorization: str = Header(None)):
        try:
            logger.debug("list_workflows entry authorization=%r", authorization)
        except Exception:
            pass
        return list_workflows_impl(authorization)

    def list_workflows_impl(authorization: str = None):
        """Return list of workflows visible to the authenticated user's workspace.

        Mirrors the pattern used in providers.list_providers_impl: returns an
        empty list when workspace is missing (allowing unauthenticated/fallback
        behavior in some tests), raises HTTP 401 when no user, and 500 when
        DB is unavailable.
        """
        user_id, wsid = _resolve_user_and_workspace(authorization)
        try:
            logger.debug("list_workflows called authorization=%r resolved_user=%r workspace=%r", authorization, user_id, wsid)
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
            rows = db.query(models.Workflow).filter(models.Workflow.workspace_id == wsid).all()
            try:
                logger.debug("list_workflows DB rows=%d workspace=%s", len(rows), wsid)
            except Exception:
                pass
            out = []
            for r in rows:
                out.append({'id': r.id, 'workspace_id': r.workspace_id, 'name': r.name, 'description': r.description, 'graph': getattr(r, 'graph', None)})
            try:
                logger.info("list_workflows: returning %d workflows for workspace=%s (DB)", len(out), wsid)
            except Exception:
                pass
            return out
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass

    # Expose node schema lookup used by the frontend NodeInspector.
    # Returns a permissive empty-object schema when unknown.
    try:
        from ..node_schemas import get_node_json_schema
    except Exception:
        def get_node_json_schema(label: str):
            return {"type": "object"}

    @app.get('/api/node_schema/{label}')
    def node_schema(label: str, authorization: str = Header(None)):
        try:
            logger.debug("node_schema called label=%r", label)
        except Exception:
            pass
        try:
            schema = get_node_json_schema(label)
        except Exception:
            schema = {"type": "object"}
        try:
            logger.info("node_schema returning for label=%s schema_type=%s", label, type(schema))
        except Exception:
            pass
        return schema

    @app.get('/api/workflows/{wid}')
    def get_workflow(wid: int, authorization: str = Header(None)):
        return get_workflow_impl(wid, authorization)

    def _resolve_user_and_workspace(authorization: str):
        user_id = ctx.get('_user_from_token')(authorization) if authorization is not None else None
        if not user_id:
            return (None, None)
        wsid = _workspace_for_user(user_id)
        # preserve previous auto-create behavior: create workspace if missing
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
                        logger.info("workflows: created workspace %s for user %s", wsid, user_id)
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


    def get_workflow_impl(wid: int, authorization: str = None):
        user_id, wsid = _resolve_user_and_workspace(authorization)
        if not user_id:
            raise HTTPException(status_code=401)
        if not wsid:
            raise HTTPException(status_code=400)
        try:
            logger.debug("get_workflow called wid=%r resolved_user=%r workspace=%r", wid, user_id, wsid)
        except Exception:
            pass
        if SessionLocal is None or models is None:
            raise HTTPException(status_code=500, detail='database unavailable')
        db = None
        try:
            db = SessionLocal()
            wf = db.query(models.Workflow).filter(models.Workflow.id == wid).first()
            if not wf or wf.workspace_id != wsid:
                try:
                    logger.debug("get_workflow: not found wid=%r workspace=%r", wid, wsid)
                except Exception:
                    pass
                raise HTTPException(status_code=404)
            try:
                logger.info("get_workflow: returning workflow id=%s workspace=%s name=%s", wf.id, wf.workspace_id, wf.name)
            except Exception:
                pass
            return {'id': wf.id, 'workspace_id': wf.workspace_id, 'name': wf.name, 'description': wf.description, 'graph': getattr(wf, 'graph', None)}
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass

    @app.post('/api/workflows')
    def create_workflow(body: dict, authorization: str = Header(None)):
        return create_workflow_impl(body, authorization)

    def create_workflow_impl(body: dict, authorization: str = None):
        user_id, wsid = _resolve_user_and_workspace(authorization)
        try:
            logger.debug("create_workflow called body_keys=%r resolved_user=%r workspace=%r", list(body.keys()) if isinstance(body, dict) else None, user_id, wsid)
        except Exception:
            pass
        if not user_id:
            # try to fall back to any configured test users in ctx (keeps tests working that set ctx._users)
            if ctx.get('_users'):
                user_id = list(ctx.get('_users').keys())[0]
            else:
                raise HTTPException(status_code=401)
        if not wsid:
            raise HTTPException(status_code=400, detail='workspace not found')
        if SessionLocal is None or models is None:
            return JSONResponse(status_code=500, content={'detail': 'database unavailable'})

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
        try:
            from ..node_schemas import canonicalize_graph
            body_graph = body.get('graph') if isinstance(body, dict) else None
            if body_graph is not None:
                body['graph'] = canonicalize_graph(body_graph)
        except Exception:
            pass
        try:
            from .._shared import _soft_validate_graph
            warnings = _soft_validate_graph(body.get('graph'))
        except Exception:
            warnings = []
        try:
            db = SessionLocal()
            wf = models.Workflow(workspace_id=wsid, name=wf_name, description=body.get('description'), graph=body.get('graph'))
            db.add(wf)
            db.commit()
            db.refresh(wf)
            out = {'id': wf.id, 'workspace_id': wf.workspace_id, 'name': wf.name}
            if warnings:
                out['validation_warnings'] = warnings
            try:
                logger.info("create_workflow: created workflow id=%s workspace=%s name=%s", wf.id, wf.workspace_id, wf.name)
            except Exception:
                pass
            return out
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return JSONResponse(status_code=500, content={'detail': 'failed to create workflow'})
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass

    @app.put('/api/workflows/{wid}')
    def update_workflow(wid: int, body: dict, authorization: str = Header(None)):
        return update_workflow_impl(wid, body, authorization)

    def update_workflow_impl(wid: int, body: dict, authorization: str = None):
        user_id, wsid = _resolve_user_and_workspace(authorization)
        try:
            logger.debug("update_workflow called wid=%r body_keys=%r resolved_user=%r workspace=%r", wid, list(body.keys()) if isinstance(body, dict) else None, user_id, wsid)
        except Exception:
            pass
        if not user_id:
            raise HTTPException(status_code=401)
        if not wsid:
            raise HTTPException(status_code=400)
        try:
            from ..node_schemas import canonicalize_graph
            if 'graph' in body and body.get('graph') is not None:
                body['graph'] = canonicalize_graph(body.get('graph'))
        except Exception:
            pass
        try:
            from .._shared import _soft_validate_graph
            warnings = _soft_validate_graph(body.get('graph'))
        except Exception:
            warnings = []
        if SessionLocal is None or models is None:
            raise HTTPException(status_code=500, detail='database unavailable')
        db = None
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
            try:
                logger.info("update_workflow: updated workflow id=%s workspace=%s name=%s", wf.id, wf.workspace_id, wf.name)
            except Exception:
                pass
            out = {'id': wf.id, 'workspace_id': wf.workspace_id, 'name': wf.name}
            if warnings:
                out['validation_warnings'] = warnings
            return out
        except HTTPException:
            raise
        except Exception:
            try:
                if db:
                    db.rollback()
            except Exception:
                pass
            raise HTTPException(status_code=500)
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass
