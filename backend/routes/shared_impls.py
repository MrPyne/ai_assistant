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
    """Create and enqueue a manual run for workflow wf_id.

    This refactored implementation keeps the original behavior but extracts
    and simplifies the node selection and enqueue logic to reduce nesting
    and make the flow easier to follow. It remains best-effort about
    enqueueing via Celery and will fall back to inline processing when
    Celery/send_task is unavailable.
    """
    user_id = _user_from_token(authorization)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401)

    # ensure the in-memory counter exists
    global _run_counter
    try:
        _run_counter
    except NameError:
        _run_counter = 0
    _run_counter += 1

    # prepare in-memory run record (used when DB not available or for quick response)
    run_id = _run_counter
    _runs[run_id] = {
        'id': run_id,
        'workflow_id': wf_id,
        'status': 'queued',
        'created_by': user_id,
        'created_at': datetime.utcnow().isoformat(),
    }

    # DB-backed path: persist run and attempt to enqueue execution via Celery
    if _DB_AVAILABLE:
        db = None
        try:
            db = SessionLocal()
            r = models.Run(workflow_id=wf_id, status='queued')
            db.add(r)
            db.commit()
            db.refresh(r)

            # store mapping so in-memory view can reference the DB id
            _runs[run_id]['db_id'] = r.id

            try:
                _add_audit(_workspace_for_user(user_id), user_id, 'create_run', object_type='run', object_id=r.id, detail='manual')
            except Exception:
                pass

            # Attempt to enqueue asynchronously after a small grace period so
            # clients can subscribe to the SSE stream.
            try:
                from .. import tasks as _tasks
            except Exception:
                _tasks = None

            try:
                grace = float(os.environ.get('RUN_START_GRACE', '0.5'))
            except Exception:
                grace = 0.5

            def _determine_start_node_for_run(run_db_id: int):
                """Return a node id to associate with the run when possible.

                Heuristics: prefer explicit cron/timer-like nodes; otherwise pick
                a node with no incoming edges; finally fall back to the first
                declared node.
                """
                try:
                    db_local = SessionLocal()
                except Exception:
                    return None
                try:
                    run_obj = db_local.query(models.Run).filter(models.Run.id == run_db_id).first()
                    if not run_obj or not getattr(run_obj, 'workflow_id', None):
                        return None
                    wf = db_local.query(models.Workflow).filter(models.Workflow.id == run_obj.workflow_id).first()
                    if not wf or not getattr(wf, 'graph', None):
                        return None
                    graph = wf.graph

                    # normalize nodes
                    raw_nodes = graph.get('nodes') if isinstance(graph, dict) else graph
                    nodes_map = {}
                    if isinstance(raw_nodes, dict):
                        nodes_map = raw_nodes
                    else:
                        for n in (raw_nodes or []):
                            if isinstance(n, dict) and 'id' in n:
                                nodes_map[n['id']] = n

                    # build incoming map
                    incoming = {}
                    raw_edges = graph.get('edges') or [] if isinstance(graph, dict) else []
                    for e in (raw_edges or []):
                        try:
                            src = e.get('source')
                            tgt = e.get('target')
                            if src and tgt:
                                incoming.setdefault(tgt, []).append(src)
                        except Exception:
                            pass

                    # prefer cron/timer nodes
                    for nid, nd in nodes_map.items():
                        try:
                            label = (nd.get('data') or {}).get('label') or nd.get('label') or ''
                            ntype = nd.get('type') or (nd.get('data') or {}).get('label')
                            if (isinstance(label, str) and 'cron' in label.lower()) or (isinstance(ntype, str) and ntype.lower() in ('timer', 'cron', 'cron trigger')):
                                return nid
                        except Exception:
                            continue

                    # nodes with no incoming edges
                    starters = [nid for nid in nodes_map.keys() if nid not in incoming]
                    if starters:
                        return starters[0]

                    # fallback to first declared node
                    if nodes_map:
                        return next(iter(nodes_map.keys()))

                except Exception:
                    try:
                        logger.exception('error while determining start node for run %s', run_db_id)
                    except Exception:
                        pass
                finally:
                    try:
                        db_local.close()
                    except Exception:
                        pass
                return None

            def _delayed_enqueue(db_run_id: int):
                # Small grace to allow SSE subscriptions
                try:
                    import time as _time
                    _time.sleep(grace)
                except Exception:
                    pass

                node_id = None
                try:
                    node_id = _determine_start_node_for_run(db_run_id)
                except Exception:
                    node_id = None

                try:
                    logger.info('manual_run enqueue determined node_id=%s for db_run_id=%s', node_id, db_run_id)
                except Exception:
                    pass

                # Best-effort publish of a node.started event scoped to node_id
                if node_id and _tasks is not None:
                    try:
                        _tasks._publish_redis_event({
                            'type': 'node',
                            'run_id': db_run_id,
                            'node_id': node_id,
                            'status': 'started',
                            'timestamp': datetime.utcnow().isoformat(),
                        })
                        logger.info('published node.started event for run=%s node=%s', db_run_id, node_id)
                    except Exception:
                        try:
                            logger.exception('failed to publish node.started event for run %s node %s', db_run_id, node_id)
                        except Exception:
                            pass

                # Try to enqueue via Celery; fall back to inline processing
                if _tasks is not None:
                    try:
                        _tasks.celery_app.send_task('execute_workflow', args=(db_run_id, node_id) if node_id else (db_run_id,))
                        logger.info('scheduled execute_workflow for db_run_id=%s node_id=%s', db_run_id, node_id)
                        return
                    except Exception:
                        try:
                            logger.exception('celery send_task failed for run %s; falling back to inline', db_run_id)
                        except Exception:
                            pass

                # Inline fallback
                try:
                    if node_id:
                        if _tasks is not None:
                            _tasks.process_run(db_run_id, node_id)
                        else:
                            # if tasks not importable, call local process_run if present
                            from ..tasks import process_run as _proc
                            _proc(db_run_id, node_id)
                        logger.info('processed execute_workflow inline for db_run_id=%s node_id=%s', db_run_id, node_id)
                    else:
                        if _tasks is not None:
                            _tasks.process_run(db_run_id)
                        else:
                            from ..tasks import process_run as _proc
                            _proc(db_run_id)
                        logger.info('processed execute_workflow inline for db_run_id=%s', db_run_id)
                except Exception:
                    try:
                        logger.exception('inline process_run failed for db_run_id=%s', db_run_id)
                    except Exception:
                        pass

            # Start background thread for enqueueing (daemon so it doesn't block shutdown)
            try:
                import threading as _threading
                t = _threading.Thread(target=_delayed_enqueue, args=(r.id,), daemon=True)
                t.start()
                try:
                    logger.info('manual_run scheduled run_id=%s delayed_start=%s', r.id, grace)
                except Exception:
                    pass
            except Exception:
                try:
                    logger.exception('failed to start enqueue thread for run %s', r.id)
                except Exception:
                    pass

            # Return DB run id for clients
            return {'run_id': r.id, 'status': 'queued'}

        except Exception:
            try:
                if db is not None:
                    db.rollback()
            except Exception:
                pass
        finally:
            try:
                if db is not None:
                    db.close()
            except Exception:
                pass

    # DB not available path: return in-memory run id
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
