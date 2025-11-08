"""Implementation helpers for provider routes.

These functions encapsulate the heavy logic previously present in
backend.routes.providers so that the route file can remain small.
Each function accepts the `common` dict produced by
backend.routes.api_common.init_ctx(ctx) to access DB and helpers.
"""
import json


def _resolve_user_and_workspace(common, ctx, authorization: str):
    SessionLocal = common.get('SessionLocal')
    models = common.get('models')
    _workspace_for_user = common.get('_workspace_for_user')
    logger = common.get('logger')

    user_id = None
    if authorization is not None:
        token_func = ctx.get('_user_from_token')
        if callable(token_func):
            user_id = token_func(authorization)
    if not user_id:
        return (None, None)

    wsid = _workspace_for_user(user_id) if callable(_workspace_for_user) else None

    if not wsid and SessionLocal is not None and models is not None:
        try:
            db = SessionLocal()
            try:
                user = db.query(models.User).filter(models.User.id == user_id).first()
                if user and getattr(user, 'email', None):
                    name = "{}-workspace".format(getattr(user, 'email'))
                else:
                    name = "user-{}-workspace".format(user_id)
                new_ws = models.Workspace(name=name, owner_id=user_id)
                db.add(new_ws)
                db.commit()
                db.refresh(new_ws)
                wsid = new_ws.id
                try:
                    if logger:
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


def get_provider_impl(common, ctx, pid: int, authorization: str = None):
    SessionLocal = common.get('SessionLocal')
    models = common.get('models')
    logger = common.get('logger')

    user_id, wsid = _resolve_user_and_workspace(common, ctx, authorization)
    if not user_id:
        raise common.get('HTTPException', Exception)(status_code=401)
    if not wsid:
        raise common.get('HTTPException', Exception)(status_code=400)
    if SessionLocal is None or models is None:
        raise common.get('HTTPException', Exception)(status_code=500, detail='database unavailable')

    db = None
    try:
        db = SessionLocal()
        p = db.query(models.Provider).filter(models.Provider.id == pid).first()
        if not p or p.workspace_id != wsid:
            raise common.get('HTTPException', Exception)(status_code=404)
        out = {
            'id': p.id,
            'workspace_id': p.workspace_id,
            'type': p.type,
            'secret_id': getattr(p, 'secret_id', None),
            'last_tested_at': getattr(p, 'last_tested_at', None),
        }
        try:
            if logger:
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


def update_provider_impl(common, ctx, pid: int, body: dict, authorization: str = None):
    SessionLocal = common.get('SessionLocal')
    models = common.get('models')
    _add_audit = common.get('_add_audit')
    logger = common.get('logger')
    encrypt_value = common.get('encrypt_value')

    user_id, wsid = _resolve_user_and_workspace(common, ctx, authorization)
    if not user_id:
        raise common.get('HTTPException', Exception)(status_code=401)
    if not wsid:
        raise common.get('HTTPException', Exception)(status_code=400)
    if SessionLocal is None or models is None:
        return common.get('JSONResponse', lambda **k: None)(status_code=500, content={'detail': 'database unavailable'})

    inline_secret = body.get('secret') if isinstance(body, dict) else None
    secret_id = body.get('secret_id') if isinstance(body, dict) else None

    if inline_secret is not None:
        try:
            secret_value = json.dumps(inline_secret)
        except Exception:
            return common.get('JSONResponse', lambda **k: None)(status_code=400, content={'detail': 'invalid secret payload'})
        db = None
        try:
            db = SessionLocal()
            enc = secret_value
            try:
                if encrypt_value is not None:
                    enc = encrypt_value(secret_value)
            except Exception:
                enc = secret_value
            s = models.Secret(workspace_id=wsid, name="provider:update", encrypted_value=enc, created_by=user_id)
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
            return common.get('JSONResponse', lambda **k: None)(status_code=500, content={'detail': 'failed to create secret'})
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
                return common.get('JSONResponse', lambda **k: None)(status_code=400, content={'detail': 'secret_id not found in workspace'})
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass

    db = None
    try:
        db = SessionLocal()
        p = db.query(models.Provider).filter(models.Provider.id == pid).first()
        if not p or p.workspace_id != wsid:
            raise common.get('HTTPException', Exception)(status_code=404)
        if isinstance(body, dict) and 'type' in body:
            p.type = body.get('type')
        if secret_id is not None:
            p.secret_id = secret_id
        if isinstance(body, dict) and 'config' in body:
            p.config = body.get('config')
        db.add(p)
        db.commit()
        try:
            if callable(_add_audit):
                _add_audit(wsid, user_id, 'update_provider', object_type='provider', object_id=p.id, detail=p.type)
        except Exception:
            pass
        try:
            if logger:
                logger.info("update_provider: updated provider id=%s workspace=%s type=%s", p.id, p.workspace_id, p.type)
        except Exception:
            pass
        return {
            'id': p.id,
            'workspace_id': p.workspace_id,
            'type': p.type,
            'secret_id': getattr(p, 'secret_id', None),
            'last_tested_at': getattr(p, 'last_tested_at', None),
        }
    except common.get('HTTPException', Exception):
        raise
    except Exception:
        try:
            if db:
                db.rollback()
        except Exception:
            pass
        return common.get('JSONResponse', lambda **k: None)(status_code=500, content={'detail': 'failed to update provider'})
    finally:
        try:
            if db:
                db.close()
        except Exception:
            pass


def create_provider_impl(common, ctx, body: dict, authorization: str = None):
    SessionLocal = common.get('SessionLocal')
    models = common.get('models')
    _add_audit = common.get('_add_audit')
    logger = common.get('logger')
    encrypt_value = common.get('encrypt_value')

    user_id, wsid = _resolve_user_and_workspace(common, ctx, authorization)
    if not user_id:
        raise common.get('HTTPException', Exception)(status_code=401)
    if not wsid:
        raise common.get('HTTPException', Exception)(status_code=400)
    if SessionLocal is None or models is None:
        return common.get('JSONResponse', lambda **k: None)(status_code=500, content={'detail': 'database unavailable'})

    secret_id = body.get('secret_id') if isinstance(body, dict) else None
    inline_secret = body.get('secret') if isinstance(body, dict) else None

    if inline_secret is not None:
        try:
            secret_value = json.dumps(inline_secret)
        except Exception:
            return common.get('JSONResponse', lambda **k: None)(status_code=400, content={'detail': 'invalid secret payload'})
        db = None
        try:
            db = SessionLocal()
            enc = secret_value
            try:
                if encrypt_value is not None:
                    enc = encrypt_value(secret_value)
            except Exception:
                enc = secret_value
            s = models.Secret(workspace_id=wsid, name="provider:{}".format(body.get('type')), encrypted_value=enc, created_by=user_id)
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
            return common.get('JSONResponse', lambda **k: None)(status_code=500, content={'detail': 'failed to create secret'})
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
                raise common.get('HTTPException', Exception)(status_code=400, detail='secret_id not found in workspace')
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
            if callable(_add_audit):
                _add_audit(wsid, user_id, 'create_provider', object_type='provider', object_id=p.id, detail=body.get('type'))
        except Exception:
            pass
        try:
            if logger:
                logger.info("create_provider: created provider id=%s workspace=%s type=%s secret_id=%s", p.id, p.workspace_id, p.type, getattr(p, 'secret_id', None))
        except Exception:
            pass
        return {'id': p.id, 'workspace_id': p.workspace_id, 'type': p.type, 'secret_id': p.secret_id}
    except Exception:
        try:
            if db:
                db.rollback()
        except Exception:
            pass
        return common.get('JSONResponse', lambda **k: None)(status_code=500, content={'detail': 'failed to create provider'})
    finally:
        try:
            if db:
                db.close()
        except Exception:
            pass


def list_providers_impl(common, ctx, authorization: str = None):
    SessionLocal = common.get('SessionLocal')
    models = common.get('models')
    logger = common.get('logger')

    user_id, wsid = _resolve_user_and_workspace(common, ctx, authorization)
    if not user_id:
        raise common.get('HTTPException', Exception)(status_code=401)
    if not wsid:
        return []
    if SessionLocal is None or models is None:
        raise common.get('HTTPException', Exception)(status_code=500, detail='database unavailable')

    db = None
    try:
        db = SessionLocal()
        rows = db.query(models.Provider).filter(models.Provider.workspace_id == wsid).all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'workspace_id': r.workspace_id,
                'type': r.type,
                'secret_id': getattr(r, 'secret_id', None),
                'last_tested_at': getattr(r, 'last_tested_at', None),
            })
        try:
            if logger:
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


def providers_test_impl(common, ctx, body: dict, authorization: str = None):
    logger = common.get('logger')
    SessionLocal = common.get('SessionLocal')
    models = common.get('models')

    user_id, wsid = _resolve_user_and_workspace(common, ctx, authorization)
    if not user_id:
        raise common.get('HTTPException', Exception)(status_code=401)
    if not wsid:
        raise common.get('HTTPException', Exception)(status_code=400)
    ptype = body.get('type') if isinstance(body, dict) else None
    if not ptype:
        return common.get('JSONResponse', lambda **k: None)(status_code=400, content={'detail': 'type required'})
    inline_secret = body.get('secret') if isinstance(body, dict) else None
    secret_id = body.get('secret_id') if isinstance(body, dict) else None
    if inline_secret is None and not secret_id:
        return common.get('JSONResponse', lambda **k: None)(status_code=400, content={'detail': 'secret or secret_id required'})
    if secret_id is not None:
        if SessionLocal is None or models is None:
            return common.get('JSONResponse', lambda **k: None)(status_code=500, content={'detail': 'database unavailable'})
        db = None
        try:
            db = SessionLocal()
            s = db.query(models.Secret).filter(models.Secret.id == secret_id).first()
            if not s or s.workspace_id != wsid:
                try:
                    if logger:
                        logger.debug("providers_test: secret_id=%s not found in workspace=%s", secret_id, wsid)
                except Exception:
                    pass
                return common.get('JSONResponse', lambda **k: None)(status_code=400, content={'detail': 'secret_id not found in workspace'})
        finally:
            try:
                if db:
                    db.close()
            except Exception:
                pass
    try:
        if logger:
            logger.info("providers.test type=%s workspace=%s user=%s", ptype, wsid, user_id)
    except Exception:
        pass
    return {'ok': True}
