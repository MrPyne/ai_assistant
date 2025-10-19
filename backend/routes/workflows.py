def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    SessionLocal = common['SessionLocal']
    models = common['models']
    _DB_AVAILABLE = common['_DB_AVAILABLE']
    _users = common['_users']
    _workflows = common['_workflows']
    _next = common['_next']
    _workspace_for_user = common['_workspace_for_user']
    logger = common['logger']
    _FASTAPI_HEADERS = common['_FASTAPI_HEADERS']

    try:
        from fastapi import HTTPException, Header
        from fastapi.responses import JSONResponse
    except Exception:
        from backend.routes.api_common import HTTPException, Header, JSONResponse  # type: ignore

    if _FASTAPI_HEADERS:
        @app.get('/api/workflows')
        def list_workflows(authorization: str = Header(None)):
            return list_workflows_impl(authorization)
    else:
        @app.get('/api/workflows')
        def list_workflows(authorization: str = None):
            return list_workflows_impl(authorization)

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
            if ctx.get('_users'):
                user_id = list(ctx.get('_users').keys())[0]
            else:
                raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400, detail='workspace not found')

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
