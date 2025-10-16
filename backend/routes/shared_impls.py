"""Implementations for shared route logic extracted from app_impl.
These functions encapsulate the DB vs in-memory fallbacks and are used by
route modules to keep them thin.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
import threading
import os
from ..utils import redact_secrets
try:
    from ..database import SessionLocal
    from .. import models
    _DB_AVAILABLE = True
except Exception:
    SessionLocal = None
    models = None
    _DB_AVAILABLE = False

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

def manual_run_impl(wf_id: int, request, authorization: Optional[str]):
    user_id = _user_from_token(authorization)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401)
    global _run_counter
    try:
        _run_counter
    except NameError:
        _run_counter = 0
    _run_counter += 1
    run_id = _run_counter
    _runs[run_id] = {
        'id': run_id,
        'workflow_id': wf_id,
        'status': 'queued',
        'created_by': user_id,
        'created_at': datetime.utcnow().isoformat(),
    }
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            r = models.Run(workflow_id=wf_id, status='queued')
            db.add(r)
            db.commit()
            db.refresh(r)
            # store mapping to DB id for in-memory view
            _runs[run_id]['db_id'] = r.id
            try:
                _add_audit(_workspace_for_user(user_id), user_id, 'create_run', object_type='run', object_id=r.id, detail='manual')
            except Exception:
                pass

            # Try to enqueue execution via Celery, but schedule slightly
            # delayed start in a background thread so clients have a short
            # window to open an SSE connection and subscribe to the run
            # channel. This reduces the race where the worker publishes
            # terminal status before the browser subscribes.
            try:
                # Import lazily to avoid adding heavy imports at module load time.
                from .. import tasks as _tasks
                import logging as _logging
                logger = _logging.getLogger(__name__)

                try:
                    grace = float(os.environ.get('RUN_START_GRACE', '0.5'))
                except Exception:
                    grace = 0.5

                def _delayed_enqueue(run_db_id):
                    # small grace period to allow clients to subscribe
                    import time as _time
                    try:
                        grace = float(os.environ.get('RUN_START_GRACE', '0.5'))
                    except Exception:
                        grace = 0.5
                    try:
                        _time.sleep(grace)
                    except Exception:
                        pass
                    try:
                        # Determine a workflow node id to associate with this run
                        # so persisted RunLog entries always reference a real
                        # workflow node. Best-effort: try to load the workflow
                        # graph from the DB and pick the first node's id. If
                        # that fails, fall back to sending the task without an
                        # explicit node_id which will cause the worker to detect
                        # (previous behavior).
                        node_id = None
                        try:
                            if _DB_AVAILABLE:
                                db = SessionLocal()
                                try:
                                    run_obj = db.query(models.Run).filter(models.Run.id == run_db_id).first()
                                    if run_obj and getattr(run_obj, 'workflow_id', None):
                                        wf = db.query(models.Workflow).filter(models.Workflow.id == run_obj.workflow_id).first()
                                        if wf and getattr(wf, 'graph', None) and isinstance(wf.graph, dict):
                                            nodes = wf.graph.get('nodes') or []
                                            if len(nodes) > 0 and isinstance(nodes[0], dict):
                                                node_id = nodes[0].get('id')
                                finally:
                                    try:
                                        db.close()
                                    except Exception:
                                        pass
                        except Exception:
                            try:
                                logger.exception('failed to determine node_id for run %s; will enqueue without explicit node_id', run_db_id)
                            except Exception:
                                pass

                        try:
                            if node_id is not None:
                                _tasks.celery_app.send_task('execute_workflow', args=(run_db_id, node_id))
                                logger.info('scheduled execute_workflow for db_run_id=%s node_id=%s', run_db_id, node_id)
                            else:
                                _tasks.celery_app.send_task('execute_workflow', args=(run_db_id,))
                                logger.info('scheduled execute_workflow for db_run_id=%s', run_db_id)
                        except Exception:
                            # If Celery isn't configured or send_task fails, process inline
                            try:
                                if node_id is not None:
                                    _tasks.process_run(run_db_id, node_id)
                                    logger.info('processed execute_workflow inline for db_run_id=%s node_id=%s', run_db_id, node_id)
                                else:
                                    _tasks.process_run(run_db_id)
                                    logger.info('processed execute_workflow inline for db_run_id=%s', run_db_id)
                            except Exception:
                                logger.exception('inline process_run failed for db_run_id=%s', run_db_id)
                    except Exception:
                        # swallow all errors; this is best-effort
                        try:
                            logger.exception('failed to enqueue run %s', run_db_id)
                        except Exception:
                            pass

                import threading as _threading
                t = _threading.Thread(target=_delayed_enqueue, args=(r.id,), daemon=True)
                t.start()
                try:
                    logger.info('manual_run scheduled run_id=%s delayed_start=%s', r.id, grace)
                except Exception:
                    pass
            except Exception:
                # best-effort only: ignore enqueue errors
                pass

            # Return the DB run id so clients subscribe to the correct stream/channel
            return {'run_id': r.id, 'status': 'queued'}
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
    return {'run_id': run_id, 'status': 'queued'}


def retry_run_impl(run_id: int, authorization: Optional[str]):
    user_id = _user_from_token(authorization)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401)
    wsid = _workspace_for_user(user_id)
    if not wsid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400)
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            orig = db.query(models.Run).filter(models.Run.id == run_id).first()
            if not orig:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail='run not found')
            wf = db.query(models.Workflow).filter(models.Workflow.id == orig.workflow_id).first()
            if not wf or wf.workspace_id != wsid:
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail='not allowed')
            new = models.Run(workflow_id=orig.workflow_id, status='queued', input_payload=getattr(orig, 'input_payload', None))
            db.add(new)
            db.commit()
            try:
                _add_audit(wsid, user_id, 'retry_run', object_type='run', object_id=new.id, detail=f'retry_of:{run_id}')
            except Exception:
                pass
            return {'run_id': new.id, 'status': 'queued'}
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

    orig = _runs.get(run_id)
    if not orig:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail='run not found')
    if orig.get('workflow_id') is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=400)
    _next['run'] += 1
    nid = _next['run']
    _runs[nid] = {'workflow_id': orig.get('workflow_id'), 'status': 'queued', 'created_by': user_id, 'created_at': datetime.utcnow().isoformat(), 'retries_of': run_id}
    try:
        _add_audit(wsid, user_id, 'retry_run', object_type='run', object_id=nid, detail=f'retry_of:{run_id}')
    except Exception:
        pass
    return {'run_id': nid, 'status': 'queued'}


def list_runs_impl(workflow_id, limit, offset, authorization):
    user_id = _user_from_token(authorization)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401)
    try:
        if _DB_AVAILABLE:
            db = SessionLocal()
            q = db.query(models.Run)
            if workflow_id is not None:
                q = q.filter(models.Run.workflow_id == workflow_id)
            total = q.count()
            rows = q.order_by(models.Run.id.desc()).offset(offset).limit(limit).all()
            items = []
            for r in rows:
                items.append({'id': r.id, 'workflow_id': r.workflow_id, 'status': r.status, 'started_at': r.started_at, 'finished_at': r.finished_at, 'attempts': getattr(r, 'attempts', None)})
            return {'items': items, 'total': total, 'limit': limit, 'offset': offset}
    except Exception:
        pass
    runs_list = []
    for rid, r in _runs.items():
        if workflow_id is None or r.get('workflow_id') == workflow_id:
            runs_list.append({'id': rid, 'workflow_id': r.get('workflow_id'), 'status': r.get('status'), 'created_at': r.get('created_at')})
    runs_list = sorted(runs_list, key=lambda x: x['id'], reverse=True)
    total = len(runs_list)
    paged = runs_list[offset: offset + limit]
    return {'items': paged, 'total': total, 'limit': limit, 'offset': offset}


def get_run_detail_impl(run_id: int, authorization: Optional[str]):
    user_id = _user_from_token(authorization)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401)
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            r = db.query(models.Run).filter(models.Run.id == run_id).first()
            if not r:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail='run not found')
            out = {
                'id': r.id,
                'workflow_id': r.workflow_id,
                'status': r.status,
                'input_payload': getattr(r, 'input_payload', None),
                'output_payload': getattr(r, 'output_payload', None),
                'started_at': getattr(r, 'started_at', None),
                'finished_at': getattr(r, 'finished_at', None),
                'attempts': getattr(r, 'attempts', None),
            }
            try:
                rows = db.query(models.RunLog).filter(models.RunLog.run_id == run_id).order_by(models.RunLog.timestamp.asc()).all()
                out_logs = []
                for rr in rows:
                    out_logs.append({'id': rr.id, 'run_id': rr.run_id, 'node_id': rr.node_id, 'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None, 'level': rr.level, 'message': rr.message})
                out['logs'] = out_logs
            except Exception:
                out['logs'] = []
            return out
        except Exception:
            pass
    r = _runs.get(run_id)
    if not r:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail='run not found')
    out = {
        'id': run_id,
        'workflow_id': r.get('workflow_id'),
        'status': r.get('status'),
        'input_payload': r.get('input_payload'),
        'output_payload': r.get('output_payload'),
        'started_at': r.get('created_at'),
        'finished_at': r.get('finished_at'),
        'attempts': r.get('attempts'),
        'logs': []
    }
    return out

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
