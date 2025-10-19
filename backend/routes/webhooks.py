def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    SessionLocal = common['SessionLocal']
    models = common['models']
    _DB_AVAILABLE = common['_DB_AVAILABLE']
    _workflows = common['_workflows']
    _webhooks = common['_webhooks']
    _runs = ctx.get('_runs')
    _next = common['_next']
    _workspace_for_user = common['_workspace_for_user']
    _add_audit = common['_add_audit']
    logger = common['logger']
    _FASTAPI_HEADERS = common['_FASTAPI_HEADERS']

    try:
        from fastapi import HTTPException, Header
    except Exception:
        from backend.routes.api_common import HTTPException, Header  # type: ignore

    # create webhook
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
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                wf = db.query(models.Workflow).filter(models.Workflow.id == wf_id).first()
                if not wf or wf.workspace_id != wsid:
                    return {'detail': 'workflow not found'}
                path_val = body.get('path') or f"{wf_id}-{_next.get('webhook', 1)}"
                w = models.Webhook(workspace_id=wsid, workflow_id=wf_id, path=path_val, description=body.get('description'))
                db.add(w)
                db.commit()
                db.refresh(w)
                try:
                    _next['webhook'] = _next.get('webhook', 1) + 1
                except Exception:
                    pass
                return {'id': w.id, 'path': w.path, 'workflow_id': wf_id}
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

    # list webhooks
    @app.get('/api/workflows/{wf_id}/webhooks')
    def list_webhooks(wf_id: int):
        out = []
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                rows = db.query(models.Webhook).filter(models.Webhook.workflow_id == wf_id).all()
                for r in rows:
                    out.append({'id': r.id, 'path': r.path, 'description': r.description, 'created_at': getattr(r, 'created_at', None)})
                return out
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        for hid, h in _webhooks.items():
            if h.get('workflow_id') == wf_id:
                out.append({'id': hid, 'path': h.get('path'), 'description': h.get('description'), 'created_at': None})
        return out

    # delete webhook
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
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                w = db.query(models.Webhook).filter(models.Webhook.id == hid).first()
                if not w or w.workflow_id != wf_id or w.workspace_id != wsid:
                    from fastapi import HTTPException
                    raise HTTPException(status_code=404)
                db.delete(w)
                db.commit()
                try:
                    _add_audit(wsid, user_id, 'delete_webhook', object_type='webhook', object_id=hid)
                except Exception:
                    pass
                return {'status': 'deleted'}
            except HTTPException:
                raise
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                from fastapi import HTTPException
                raise HTTPException(status_code=500)
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        row = _webhooks.get(hid)
        if not row or row.get('workflow_id') != wf_id:
            raise HTTPException(status_code=404)
        del _webhooks[hid]
        try:
            _add_audit(wsid, user_id, 'delete_webhook', object_type='webhook', object_id=hid)
        except Exception:
            pass
        return {'status': 'deleted'}

    # public webhook trigger
    if _FASTAPI_HEADERS:
        @app.post('/api/webhook/{workflow_id}/{trigger_id}')
        def public_webhook_trigger(workflow_id: int, trigger_id: str, body: dict, authorization: str = Header(None)):
            return public_webhook_trigger_impl(workflow_id, trigger_id, body, authorization)
    else:
        @app.post('/api/webhook/{workflow_id}/{trigger_id}')
        def public_webhook_trigger(workflow_id: int, trigger_id: str, body: dict, authorization: str = None):
            return public_webhook_trigger_impl(workflow_id, trigger_id, body, authorization)

    def public_webhook_trigger_impl(workflow_id: int, trigger_id: str, body: dict, authorization: str = None):
        user_id = None
        try:
            user_id = ctx.get('_user_from_token')(authorization)
        except Exception:
            user_id = None
        wsid = None
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                try:
                    w = db.query(models.Webhook).filter(models.Webhook.workflow_id == workflow_id, models.Webhook.path == trigger_id).first()
                    if w:
                        wsid = getattr(w, 'workspace_id', None)
                except Exception:
                    wsid = None
                r = models.Run(workflow_id=workflow_id, status='queued')
                db.add(r)
                db.commit()
                db.refresh(r)
                try:
                    _add_audit(wsid, user_id, 'create_run', object_type='run', object_id=r.id, detail='trigger')
                except Exception:
                    pass
                return {'run_id': r.id, 'status': 'queued'}
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        run_id = _next.get('run', 1)
        _next['run'] = run_id + 1
        _runs[run_id] = {'workflow_id': workflow_id, 'status': 'queued'}
        try:
            wsid = _workflows.get(workflow_id, {}).get('workspace_id')
        except Exception:
            wsid = None
        try:
            _add_audit(wsid, user_id, 'create_run', object_type='run', object_id=run_id, detail='trigger')
        except Exception:
            pass
        return {'run_id': run_id, 'status': 'queued'}
