"""Implementations for shared route logic extracted from app_impl.
These functions encapsulate the DB vs in-memory fallbacks and are used by
route modules to keep them thin.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
import threading
import os
from ..utils import redact_secrets
import logging
try:
    from ..database import SessionLocal
    from .. import models
    _DB_AVAILABLE = True
except Exception:
    SessionLocal = None
    models = None
    _DB_AVAILABLE = False

logger = logging.getLogger(__name__)

# reuse simple in-memory stores local to this module to avoid circular imports
_runs: Dict[int, Dict[str, Any]] = {}
_next = {'user': 1, 'ws': 1, 'scheduler': 1, 'run': 1, 'provider': 1, 'secret': 1, 'workflow': 1, 'webhook': 1}
_users: Dict[int, Dict[str, Any]] = {}
_workspaces: Dict[int, Dict[str, Any]] = {}
_schedulers: Dict[int, Dict[str, Any]] = {}
_providers: Dict[int, Dict[str, Any]] = {}
_secrets: Dict[int, Dict[str, Any]] = {}
_workflows: Dict[int, Dict[str, Any]] = {}
_webhooks: Dict[int, Dict[str, Any]] = {}

# simple run counter used by new impls during migration
_run_counter = 0

import hashlib as _hashlib

def hash_password(password) -> str:
    if isinstance(password, bytes):
        try:
            password = password.decode('utf-8')
        except Exception:
            password = password.decode('latin-1')
    if not isinstance(password, str):
        password = str(password)
    salt = os.environ.get('PASSWORD_SALT', 'testsalt').encode()
    dk = _hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return dk.hex()

def verify_password(password, hashed: str) -> bool:
    return hash_password(password) == hashed

# basic token helpers

def _user_from_token(authorization: Optional[str]) -> Optional[int]:
    if not authorization:
        return None
    parts = authorization.split()
    token = parts[1] if len(parts) == 2 else parts[0]
    if token.startswith('token-'):
        try:
            return int(token.split('-', 1)[1])
        except Exception:
            return None
    return None


def _workspace_for_user(user_id: int) -> Optional[int]:
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            ws = db.query(models.Workspace).filter(models.Workspace.owner_id == user_id).first()
            if ws:
                return ws.id
        except Exception:
            pass
        finally:
            try:
                db.close()
            except Exception:
                pass
    for wid, w in _workspaces.items():
        if w.get('owner_id') == user_id:
            return wid
    return None


def _add_audit(workspace_id, user_id, action, object_type=None, object_id=None, detail=None):
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            al = models.AuditLog(workspace_id=workspace_id, user_id=user_id, action=action, object_type=object_type, object_id=object_id, detail=detail)
            db.add(al)
            db.commit()
            return
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
    return

# Implementations
# The manual_run_impl implementation has been moved into backend.routes.impls
# to allow incremental refactoring without breaking imports. Import it lazily
# so tests and callers that still import shared_impls get the same object.
try:
    from .impls.run_impl import manual_run_impl  # type: ignore
except Exception:
    # If the impl cannot be imported (e.g., during partial migrations), fall
    # back to a simple shim that raises an informative error when invoked.
    def manual_run_impl(*args, **kwargs):
        raise RuntimeError('manual_run_impl implementation not available')


try:
    from .impls.run_impl import retry_run_impl as _retry_run_impl  # type: ignore

    def retry_run_impl(run_id: int, authorization: Optional[str]):
        return _retry_run_impl(run_id, authorization)
except Exception:
    def retry_run_impl(*args, **kwargs):
        raise RuntimeError('retry_run_impl implementation not available')


try:
    from .impls.run_impl import list_runs_impl as _list_runs_impl  # type: ignore

    def list_runs_impl(workflow_id, limit, offset, authorization):
        return _list_runs_impl(workflow_id, limit, offset, authorization)
except Exception:
    def list_runs_impl(*args, **kwargs):
        raise RuntimeError('list_runs_impl implementation not available')


try:
    from .impls.run_impl import get_run_detail_impl as _get_run_detail_impl  # type: ignore

    def get_run_detail_impl(run_id: int, authorization: Optional[str]):
        return _get_run_detail_impl(run_id, authorization)
except Exception:
    def get_run_detail_impl(*args, **kwargs):
        raise RuntimeError('get_run_detail_impl implementation not available')

# Scheduler impls

def create_scheduler_impl(body, user_id):
    wid = body.get('workflow_id')
    if not wid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400)
    wsid = _workspace_for_user(user_id)
    if not wsid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400)
    if _DB_AVAILABLE:
        try:
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
                db.rollback()
            except Exception:
                pass
            return {'detail': 'failed to create scheduler'}
        finally:
            try:
                db.close()
            except Exception:
                pass
    sid = _next.get('scheduler', 1)
    _next['scheduler'] = sid + 1
    _schedulers[sid] = {'workspace_id': wsid, 'workflow_id': wid, 'schedule': body.get('schedule'), 'description': body.get('description'), 'active': 1, 'created_at': None, 'last_run': None}
    try:
        _add_audit(wsid, user_id, 'create_scheduler', object_type='scheduler', object_id=sid, detail=body.get('schedule'))
    except Exception:
        pass
    return {'id': sid, 'workflow_id': wid, 'schedule': body.get('schedule')}


def list_scheduler_impl(wsid):
    if _DB_AVAILABLE:
        try:
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
                db.close()
            except Exception:
                pass
    items = []
    for sid, s in _schedulers.items():
        if s.get('workspace_id') == wsid:
            obj = dict(s)
            obj['id'] = sid
            items.append(obj)
    return items


def update_scheduler_impl(sid, body, wsid):
    if _DB_AVAILABLE:
        try:
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
    s = _schedulers.get(sid)
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
    if _DB_AVAILABLE:
        try:
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
    if sid not in _schedulers or _schedulers.get(sid).get('workspace_id') != wsid:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    del _schedulers[sid]
    try:
        _add_audit(wsid, None, 'delete_scheduler', object_type='scheduler', object_id=sid)
    except Exception:
        pass
    return {'status': 'deleted'}
