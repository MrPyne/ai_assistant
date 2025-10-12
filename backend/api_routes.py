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

    # Helper: minimal encrypt/decrypt when DB-backed
    try:
        from .crypto import encrypt_value, decrypt_value
    except Exception:
        encrypt_value = None
        decrypt_value = None

    # /api/me
    @app.get('/api/me')
    def _me(authorization: str = None):
        # Try to reuse app_impl helper _user_from_token via ctx if present
        _user_from_token = ctx.get('_user_from_token')
        uid = None
        try:
            uid = _user_from_token(authorization)
        except Exception:
            uid = None
        if not uid:
            # FastAPI usually returns 401; keep simple behaviour
            from .app_impl import HTTPException
            raise HTTPException(status_code=401)

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                u = db.query(models.User).filter(models.User.id == uid).first()
                if not u:
                    from .app_impl import HTTPException
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
            from .app_impl import HTTPException
            raise HTTPException(status_code=404)
        # find workspace
        ws_name = None
        for wid, w in _workspaces.items():
            if w.get('owner_id') == uid:
                ws_name = w.get('name')
                break
        return {'email': u.get('email'), 'workspace': ws_name}

    # Secrets: POST /api/secrets, GET /api/secrets, DELETE /api/secrets/{id}
    @app.post('/api/secrets')
    def create_secret(body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            from .app_impl import HTTPException
            raise HTTPException(status_code=401)
        # find workspace
        wsid = _workspace_for_user(user_id)
        if not wsid:
            from .app_impl import HTTPException
            raise HTTPException(status_code=400, detail='Workspace not found')

        name = body.get('name')
        value = body.get('value')
        if not name or value is None:
            from .app_impl import JSONResponse
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
                from .app_impl import JSONResponse
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

    @app.get('/api/secrets')
    def list_secrets(authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            from .app_impl import HTTPException
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            return []

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                rows = db.query(models.Secret).filter(models.Secret.workspace_id == wsid).all()
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
        return items

    @app.delete('/api/secrets/{sid}')
    def delete_secret(sid: int, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            from .app_impl import HTTPException
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            from .app_impl import HTTPException
            raise HTTPException(status_code=400)

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                s = db.query(models.Secret).filter(models.Secret.id == sid).first()
                if not s or s.workspace_id != wsid:
                    from .app_impl import HTTPException
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
                from .app_impl import HTTPException
                raise HTTPException(status_code=500)
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        s = _secrets.get(sid)
        if not s or s.get('workspace_id') != wsid:
            from .app_impl import HTTPException
            raise HTTPException(status_code=404)
        del _secrets[sid]
        try:
            _add_audit(wsid, user_id, 'delete_secret', object_type='secret', object_id=sid)
        except Exception:
            pass
        return {'status': 'deleted'}

    # Providers: GET /api/providers, POST /api/providers
    @app.post('/api/providers')
    def create_provider(body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        # allow provider creation without an authenticated user for some client flows
        if not user_id:
            # fallback: if no user exists yet, try to default to first user in _users
            if _users:
                user_id = list(_users.keys())[0]
            else:
                from .app_impl import HTTPException
                raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            from .app_impl import HTTPException
            raise HTTPException(status_code=400)

        secret_id = body.get('secret_id')
        if secret_id is not None:
            # validate secret ownership
            if _DB_AVAILABLE:
                try:
                    db = SessionLocal()
                    s = db.query(models.Secret).filter(models.Secret.id == secret_id, models.Secret.workspace_id == wsid).first()
                    if not s:
                        from .app_impl import HTTPException
                        raise HTTPException(status_code=400, detail='secret_id not found in workspace')
                finally:
                    try:
                        db.close()
                    except Exception:
                        pass
            else:
                s = _secrets.get(secret_id)
                if not s or s.get('workspace_id') != wsid:
                    from .app_impl import HTTPException
                    raise HTTPException(status_code=400, detail='secret_id not found in workspace')

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                p = models.Provider(workspace_id=wsid, type=body.get('type'), secret_id=secret_id, config=body.get('config'))
                db.add(p)
                db.commit()
                db.refresh(p)
                return {'id': p.id, 'workspace_id': p.workspace_id, 'type': p.type, 'secret_id': p.secret_id}
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                from .app_impl import JSONResponse
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

    @app.get('/api/providers')
    def list_providers(authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            from .app_impl import HTTPException
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            return []

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                rows = db.query(models.Provider).filter(models.Provider.workspace_id == wsid).all()
                out = []
                for r in rows:
                    out.append({'id': r.id, 'workspace_id': r.workspace_id, 'type': r.type, 'secret_id': getattr(r, 'secret_id', None)})
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
        return items

    # Workflows: GET /api/workflows, POST /api/workflows, PUT /api/workflows/{id}
    @app.get('/api/workflows')
    def list_workflows(authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        # allow unauthenticated list to return empty
        if not user_id:
            return []
        wsid = _workspace_for_user(user_id)
        if not wsid:
            return []
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                rows = db.query(models.Workflow).filter(models.Workflow.workspace_id == wsid).all()
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
        return items

    @app.post('/api/workflows')
    def create_workflow(body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            # allow creating a default user like DummyClient does
            if _users:
                user_id = list(_users.keys())[0]
            else:
                from .app_impl import HTTPException
                raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            from .app_impl import HTTPException
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
                from .app_impl import JSONResponse
                return JSONResponse(status_code=400, content={'detail': msg, 'message': msg})

        v = _validate_graph(body.get('graph'))
        if v is not None:
            detail = v[0]
            if isinstance(detail, dict):
                body_out = dict(detail)
                body_out['detail'] = detail
            else:
                body_out = {'message': str(detail), 'detail': detail}
            from .app_impl import JSONResponse
            return JSONResponse(status_code=400, content=body_out)

        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                wf = models.Workflow(workspace_id=wsid, name=body.get('name'), description=body.get('description'), graph=body.get('graph'))
                db.add(wf)
                db.commit()
                db.refresh(wf)
                return {'id': wf.id, 'workspace_id': wf.workspace_id, 'name': wf.name}
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                from .app_impl import JSONResponse
                return JSONResponse(status_code=500, content={'detail': 'failed to create workflow'})
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        wid = _next.get('workflow', 1)
        _next['workflow'] = wid + 1
        _workflows[wid] = {'workspace_id': wsid, 'name': body.get('name'), 'description': body.get('description'), 'graph': body.get('graph')}
        return {'id': wid, 'workspace_id': wsid, 'name': body.get('name')}

    @app.put('/api/workflows/{wid}')
    def update_workflow(wid: int, body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            from .app_impl import HTTPException
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
                if 'name' in body:
                    wf.name = body.get('name')
                if 'description' in body:
                    wf.description = body.get('description')
                if 'graph' in body:
                    wf.graph = body.get('graph')
                db.add(wf)
                db.commit()
                return {'id': wf.id, 'workspace_id': wf.workspace_id, 'name': wf.name}
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
            from .app_impl import HTTPException
            raise HTTPException(status_code=404)
        if 'name' in body:
            wf['name'] = body.get('name')
        if 'description' in body:
            wf['description'] = body.get('description')
        if 'graph' in body:
            wf['graph'] = body.get('graph')
        return {'id': wid, 'workspace_id': wf.get('workspace_id'), 'name': wf.get('name')}

    # Webhooks: create/list/delete per-workflow and public trigger
    @app.post('/api/workflows/{wf_id}/webhooks')
    def create_webhook(wf_id: int, body: dict, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            from .app_impl import HTTPException
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
                from .app_impl import HTTPException
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

    @app.delete('/api/workflows/{wf_id}/webhooks/{hid}')
    def delete_webhook(wf_id: int, hid: int, authorization: str = None):
        user_id = ctx.get('_user_from_token')(authorization)
        if not user_id:
            from .app_impl import HTTPException
            raise HTTPException(status_code=401)
        wsid = _workspace_for_user(user_id)
        if not wsid:
            raise HTTPException(status_code=400)
        row = _webhooks.get(hid)
        if not row or row.get('workflow_id') != wf_id:
            from .app_impl import HTTPException
            raise HTTPException(status_code=404)
        del _webhooks[hid]
        return {'status': 'deleted'}

    @app.post('/api/webhook/{workflow_id}/{trigger_id}')
    def public_webhook_trigger(workflow_id: int, trigger_id: str, body: dict, authorization: str = None):
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

