from typing import Optional
from datetime import datetime
import logging
from .auth_helpers import _workspace_for_user, _add_audit

logger = logging.getLogger(__name__)


def create_scheduler_impl(body, user_id):
    from .. import shared_impls as _shared

    wid = body.get('workflow_id')
    if not wid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400)
    wsid = _workspace_for_user(user_id)
    if not wsid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400)
    if getattr(_shared, '_DB_AVAILABLE', False):
        db = None
        try:
            SessionLocal = getattr(_shared, 'SessionLocal', None)
            models = getattr(_shared, 'models', None)
            db = SessionLocal()
            wf = db.query(models.Workflow).filter(models.Workflow.id == wid).first()
            if not wf or wf.workspace_id != wsid:
                return {'detail': 'workflow not found in workspace'}
            s = models.SchedulerEntry(workspace_id=wsid, workflow_id=wid, schedule=body.get('schedule'), description=body.get('description'), active=1)
            db.add(s)
            db.commit()
            db.refresh(s)
            try:
                _add_audit(wsid, user_id, 'create_scheduler', object_type='scheduler', object_id=s.id, detail=body.get('schedule'))
            except Exception:
                pass
            return {'id': s.id, 'workflow_id': wid, 'schedule': s.schedule}
        except Exception:
            try:
                if db is not None:
                    db.rollback()
            except Exception:
                pass
            return {'detail': 'failed to create scheduler'}
        finally:
            try:
                if db is not None:
                    db.close()
            except Exception:
                pass
    sid = _shared._next.get('scheduler', 1)
    _shared._next['scheduler'] = sid + 1
    _shared._schedulers[sid] = {'workspace_id': wsid, 'workflow_id': wid, 'schedule': body.get('schedule'), 'description': body.get('description'), 'active': 1, 'created_at': None, 'last_run': None}
    try:
        _add_audit(wsid, user_id, 'create_scheduler', object_type='scheduler', object_id=sid, detail=body.get('schedule'))
    except Exception:
        pass
    return {'id': sid, 'workflow_id': wid, 'schedule': body.get('schedule')}


def list_scheduler_impl(wsid):
    from .. import shared_impls as _shared

    if getattr(_shared, '_DB_AVAILABLE', False):
        db = None
        try:
            SessionLocal = getattr(_shared, 'SessionLocal', None)
            models = getattr(_shared, 'models', None)
            db = SessionLocal()
            rows = db.query(models.SchedulerEntry).filter(models.SchedulerEntry.workspace_id == wsid).all()
            out = []
            for r in rows:
                out.append({'id': r.id, 'workflow_id': r.workflow_id, 'schedule': r.schedule, 'description': r.description, 'active': bool(r.active)})
            return out
        except Exception:
            return []
        finally:
            try:
                if db is not None:
                    db.close()
            except Exception:
                pass
    items = []
    for sid, s in _shared._schedulers.items():
        if s.get('workspace_id') == wsid:
            obj = dict(s)
            obj['id'] = sid
            items.append(obj)
    return items


def update_scheduler_impl(sid, body, wsid):
    from .. import shared_impls as _shared

    if getattr(_shared, '_DB_AVAILABLE', False):
        db = None
        try:
            SessionLocal = getattr(_shared, 'SessionLocal', None)
            models = getattr(_shared, 'models', None)
            db = SessionLocal()
            s = db.query(models.SchedulerEntry).filter(models.SchedulerEntry.id == sid).first()
            if not s or s.workspace_id != wsid:
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            if 'schedule' in body:
                s.schedule = body.get('schedule')
            if 'description' in body:
                s.description = body.get('description')
            if 'active' in body:
                s.active = 1 if body.get('active') else 0
            db.add(s)
            db.commit()
            return {'id': s.id, 'workflow_id': s.workflow_id, 'schedule': s.schedule, 'active': bool(s.active)}
        except Exception:
            try:
                if db is not None:
                    db.rollback()
            except Exception:
                pass
            from fastapi import HTTPException
            raise HTTPException(status_code=500)
        finally:
            try:
                if db is not None:
                    db.close()
            except Exception:
                pass
    s = _shared._schedulers.get(sid)
    if not s or s.get('workspace_id') != wsid:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    if 'schedule' in body:
        s['schedule'] = body.get('schedule')
    if 'description' in body:
        s['description'] = body.get('description')
    if 'active' in body:
        s['active'] = 1 if body.get('active') else 0
    obj = dict(s)
    obj['id'] = sid
    return obj


def delete_scheduler_impl(sid, wsid):
    from .. import shared_impls as _shared

    if getattr(_shared, '_DB_AVAILABLE', False):
        db = None
        try:
            SessionLocal = getattr(_shared, 'SessionLocal', None)
            models = getattr(_shared, 'models', None)
            db = SessionLocal()
            s = db.query(models.SchedulerEntry).filter(models.SchedulerEntry.id == sid).first()
            if not s or s.workspace_id != wsid:
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            db.delete(s)
            db.commit()
            try:
                _add_audit(wsid, None, 'delete_scheduler', object_type='scheduler', object_id=sid)
            except Exception:
                pass
            return {'status': 'deleted'}
        except Exception:
            try:
                if db is not None:
                    db.rollback()
            except Exception:
                pass
            from fastapi import HTTPException
            raise HTTPException(status_code=500)
        finally:
            try:
                if db is not None:
                    db.close()
            except Exception:
                pass
    if sid not in _shared._schedulers or _shared._schedulers.get(sid).get('workspace_id') != wsid:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    del _shared._schedulers[sid]
    try:
        _add_audit(wsid, None, 'delete_scheduler', object_type='scheduler', object_id=sid)
    except Exception:
        pass
    return {'status': 'deleted'}
