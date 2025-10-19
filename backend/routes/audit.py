def register(app, ctx):
    common = __import__('backend.routes.api_common', fromlist=['']).init_ctx(ctx)
    SessionLocal = common['SessionLocal']
    models = common['models']
    _DB_AVAILABLE = common['_DB_AVAILABLE']
    _workspace_for_user = common['_workspace_for_user']
    _add_audit = common['_add_audit']
    logger = common['logger']
    _FASTAPI_HEADERS = common['_FASTAPI_HEADERS']

    try:
        from fastapi import HTTPException, Header
    except Exception:
        from backend.routes.api_common import HTTPException, Header  # type: ignore

    if _FASTAPI_HEADERS:
        @app.get('/api/audit_logs')
        def list_audit_logs(limit: int = 50, offset: int = 0, action: str = None, object_type: str = None, user_id: int = None, date_from: str = None, date_to: str = None, authorization: str = Header(None)):
            return list_audit_logs_impl(limit, offset, action, object_type, user_id, date_from, date_to, authorization)
    else:
        @app.get('/api/audit_logs')
        def list_audit_logs(limit: int = 50, offset: int = 0, action: str = None, object_type: str = None, user_id: int = None, date_from: str = None, date_to: str = None, authorization: str = None):
            return list_audit_logs_impl(limit, offset, action, object_type, user_id, date_from, date_to, authorization)

    def list_audit_logs_impl(limit: int = 50, offset: int = 0, action: str = None, object_type: str = None, user_id: int = None, date_from: str = None, date_to: str = None, authorization: str = None):
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
            _users_local = ctx.get('_users') or {}
            u = _users_local.get(uid)
            if u and u.get('role') == 'admin':
                is_admin = True
        if not is_admin:
            raise HTTPException(status_code=403)
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
