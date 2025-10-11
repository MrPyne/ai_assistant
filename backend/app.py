try:
    from fastapi import FastAPI, Request, Header, HTTPException
except Exception:
    # Allow importing backend.app in lightweight test environments where
    # FastAPI may not be installed. Provide minimal stand-ins so modules
    # that import symbols from this file (e.g., tests) can still load.
    class FastAPI:  # pragma: no cover - only used in lightweight imports
        def __init__(self, *args, **kwargs):
            pass
        def on_event(self, name):
            def _decor(fn):
                return fn
            return _decor
        def post(self, path):
            def _decor(fn):
                return fn
            return _decor
        def get(self, path):
            def _decor(fn):
                return fn
            return _decor
        def put(self, path):
            def _decor(fn):
                return fn
            return _decor
        def delete(self, path):
            def _decor(fn):
                return fn
            return _decor

    class Request:  # pragma: no cover
        pass

    def Header(default=None):  # pragma: no cover
        return None

    class HTTPException(Exception):  # pragma: no cover
        def __init__(self, status_code: int = 500, detail: str = None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
from typing import Optional, Dict, Any, List
from datetime import datetime
import threading
import time
import os

# Try to import DB helpers when available (tests run with and without DB)
try:
    from .database import SessionLocal
    from . import models
    _DB_AVAILABLE = True
except Exception:
    SessionLocal = None
    models = None
    _DB_AVAILABLE = False

app = FastAPI()

# Simple in-memory run store used when a DB is not available.
_runs: Dict[int, Dict[str, Any]] = {}
_run_counter = 0

# Minimal in-memory user/workspace/provider/secret/scheduler stores used by
# lightweight tests and by the DummyClient fallback in tests/conftest.py.
_users: Dict[int, Dict[str, Any]] = {}
_workspaces: Dict[int, Dict[str, Any]] = {}
_schedulers: Dict[int, Dict[str, Any]] = {}
_providers: Dict[int, Dict[str, Any]] = {}
_secrets: Dict[int, Dict[str, Any]] = {}
_workflows: Dict[int, Dict[str, Any]] = {}
_webhooks: Dict[int, Dict[str, Any]] = {}
_next = {'user': 1, 'ws': 1, 'scheduler': 1, 'run': 1, 'provider': 1, 'secret': 1, 'workflow': 1, 'webhook': 1}

# Scheduler thread controls
_scheduler_stop_event = threading.Event()
_scheduler_thread = None


def _user_from_token(authorization: Optional[str]) -> Optional[int]:
    # Accept tokens of the form 'token-{id}' or 'Bearer token-{id}' for tests
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
    # prefer DB lookup when available
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
    # best-effort audit insertion to DB when available; otherwise no-op for now
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


# Password helpers used by tests
import hashlib as _hashlib


def hash_password(password) -> str:
    """Simple pbkdf2-hmac-sha256 based helper used by tests. Accepts str or bytes.
    Not intended for production use; kept minimal to satisfy unit tests.
    """
    if isinstance(password, bytes):
        try:
            password = password.decode('utf-8')
        except Exception:
            # latin-1 fallback for arbitrary bytes
            password = password.decode('latin-1')
    if not isinstance(password, str):
        password = str(password)
    salt = os.environ.get('PASSWORD_SALT', 'testsalt').encode()
    dk = _hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return dk.hex()


def verify_password(password, hashed: str) -> bool:
    return hash_password(password) == hashed
    return


def _poll_schedulers(poll_interval: float = 1.0):
    """Background poller that checks scheduler entries and enqueues runs.
    For MVP we support simple interval schedules expressed as integer seconds.
    """
    while not _scheduler_stop_event.is_set():
        now_ts = time.time()
        try:
            # DB-backed schedulers preferred when available
            if _DB_AVAILABLE:
                try:
                    db = SessionLocal()
                    rows = db.query(models.SchedulerEntry).filter(models.SchedulerEntry.active == 1).all()
                    for s in rows:
                        try:
                            sched = s.schedule
                            if sched is None:
                                continue
                            try:
                                interval = int(sched)
                            except Exception:
                                continue
                            last = s.last_run_at
                            last_ts = last.timestamp() if last is not None else 0
                            if now_ts - last_ts >= interval:
                                # ensure workflow exists
                                wf = db.query(models.Workflow).filter(models.Workflow.id == s.workflow_id).first()
                                if not wf:
                                    continue
                                run = models.Run(workflow_id=s.workflow_id, status='queued')
                                db.add(run)
                                s.last_run_at = datetime.utcnow()
                                db.add(s)
                                db.commit()
                                try:
                                    _add_audit(s.workspace_id, None, 'create_run', object_type='run', object_id=run.id, detail=f'scheduler:{s.id}')
                                except Exception:
                                    pass
                        except Exception:
                            try:
                                db.rollback()
                            except Exception:
                                pass
                            continue
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

            # fallback: in-memory schedulers
            for sid, s in list(_schedulers.items()):
                try:
                    if not s.get('active'):
                        continue
                    sched = s.get('schedule')
                    if sched is None:
                        continue
                    try:
                        interval = int(sched)
                    except Exception:
                        continue
                    last = s.get('last_run', 0)
                    if now_ts - last >= interval:
                        wid = s.get('workflow_id')
                        if not wid:
                            continue
                        wf = None
                        if _DB_AVAILABLE:
                            try:
                                db = SessionLocal()
                                wf = db.query(models.Workflow).filter(models.Workflow.id == wid).first()
                            except Exception:
                                pass
                            finally:
                                try:
                                    db.close()
                                except Exception:
                                    pass
                        else:
                            wf = None
                        # if workflow exists (or we assume it does in-memory) create run
                        rid = None
                        if _DB_AVAILABLE and wf:
                            try:
                                db = SessionLocal()
                                run = models.Run(workflow_id=wid, status='queued')
                                db.add(run)
                                db.commit()
                                rid = run.id
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
                        else:
                            _next['run'] += 1
                            rid = _next['run']
                            _runs[rid] = {'workflow_id': wid, 'status': 'queued', 'via_scheduler': sid}
                        s['last_run'] = now_ts
                        try:
                            _add_audit(s.get('workspace_id'), None, 'create_run', object_type='run', object_id=rid, detail=f'scheduler:{sid}')
                        except Exception:
                            pass
                except Exception:
                    continue
        except Exception:
            pass
        _scheduler_stop_event.wait(poll_interval)


@app.on_event('startup')
def _start_scheduler_thread():
    global _scheduler_thread
    if _scheduler_thread is None:
        _scheduler_stop_event.clear()
        t = threading.Thread(target=_poll_schedulers, name='scheduler-poller', daemon=True)
        _scheduler_thread = t
        t.start()


@app.on_event('shutdown')
def _stop_scheduler_thread():
    _scheduler_stop_event.set()
    global _scheduler_thread
    try:
        if _scheduler_thread is not None:
            _scheduler_thread.join(timeout=2.0)
    finally:
        _scheduler_thread = None


@app.post('/api/workflows/{wf_id}/run')
def manual_run(wf_id: int, request: Request, authorization: Optional[str] = Header(None)):
    """Schedule a manual run for workflow `wf_id`.
    Minimal implementation: create an in-memory run and return it queued.
    """
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)

    global _run_counter
    _run_counter += 1
    run_id = _run_counter
    _runs[run_id] = {
        'id': run_id,
        'workflow_id': wf_id,
        'status': 'queued',
        'created_by': user_id,
        'created_at': datetime.utcnow().isoformat(),
    }
    # attempt to persist Run to DB when available
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            r = models.Run(workflow_id=wf_id, status='queued')
            db.add(r)
            db.commit()
            # mirror in-memory id mapping for consistency where possible
            _runs[run_id]['db_id'] = r.id
            _add_audit(_workspace_for_user(user_id), user_id, 'create_run', object_type='run', object_id=r.id, detail='manual')
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


@app.get('/api/runs')
def list_runs(workflow_id: Optional[int] = None, limit: Optional[int] = 50, offset: Optional[int] = 0, authorization: Optional[str] = Header(None)):
    """List runs. Prefer DB-backed listing when available; otherwise use in-memory store.
    """
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)

    # If DB is available this implementation would query it. For now, use
    # the in-memory store so the endpoint works reliably in tests.
    try:
        # prefer DB-backed listing when available
        if _DB_AVAILABLE:
            try:
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
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        runs: List[Dict[str, Any]] = []
        for rid, r in _runs.items():
            if workflow_id is None or r.get('workflow_id') == workflow_id:
                runs.append({'id': rid, 'workflow_id': r.get('workflow_id'), 'status': r.get('status'), 'created_at': r.get('created_at')})
        runs = sorted(runs, key=lambda x: x['id'], reverse=True)
        total = len(runs)
        paged = runs[offset: offset + limit]
        return {'items': paged, 'total': total, 'limit': limit, 'offset': offset}
    except Exception:
        return {'items': [], 'total': 0, 'limit': limit, 'offset': offset}


@app.get('/api/runs/{run_id}/logs')
def get_run_logs(run_id: int):
    """Return per-run logs. No authentication required for this minimal implementation.
    """
    try:
        # No persistent logs in this lightweight implementation.
        return {'logs': []}
    except Exception:
        return {'logs': []}


@app.get('/api/runs/{run_id}')
def get_run_detail(run_id: int, authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)

    try:
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                r = db.query(models.Run).filter(models.Run.id == run_id).first()
                if not r:
                    raise HTTPException(status_code=404, detail='run not found')
                out = {
                    'id': r.id,
                    'workflow_id': r.workflow_id,
                    'status': r.status,
                    'input_payload': r.input_payload,
                    'output_payload': r.output_payload,
                    'started_at': r.started_at,
                    'finished_at': r.finished_at,
                    'attempts': getattr(r, 'attempts', None),
                }
                # attach logs
                rows = db.query(models.RunLog).filter(models.RunLog.run_id == run_id).order_by(models.RunLog.timestamp.asc()).all()
                out_logs = []
                for rr in rows:
                    out_logs.append({'id': rr.id, 'run_id': rr.run_id, 'node_id': rr.node_id, 'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None, 'level': rr.level, 'message': rr.message})
                out['logs'] = out_logs
                return out
            except HTTPException:
                raise
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

        # fallback to in-memory run
        r = _runs.get(run_id)
        if not r:
            raise HTTPException(status_code=404, detail='run not found')
        out = {'id': run_id, 'workflow_id': r.get('workflow_id'), 'status': r.get('status'), 'input_payload': None, 'output_payload': None, 'started_at': None, 'finished_at': None, 'attempts': None, 'logs': []}
        return out
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail='internal error')


@app.post('/api/providers')
def create_provider(body: dict, authorization: Optional[str] = Header(None)):
    # require authentication for provider creation
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)

    wsid = _workspace_for_user(user_id)
    if not wsid:
        raise HTTPException(status_code=400, detail='Workspace not found')

    secret_id = body.get('secret_id')
    # validate secret exists in workspace if provided
    if secret_id is not None:
        ok = False
        # prefer DB when available
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                s = db.query(models.Secret).filter(models.Secret.id == secret_id, models.Secret.workspace_id == wsid).first()
                if s:
                    ok = True
            except Exception:
                pass
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        else:
            s = None
            if isinstance(secret_id, int):
                s = _secrets.get(secret_id)
            if s and s.get('workspace_id') == wsid:
                ok = True
        if not ok:
            raise HTTPException(status_code=400, detail='secret_id not found in workspace')

    # create in-memory provider
    pid = _next.get('provider', 1)
    _next['provider'] = pid + 1
    _providers[pid] = {'workspace_id': wsid, 'type': body.get('type'), 'secret_id': secret_id, 'config': body.get('config')}

    # attempt to persist to DB if available
    created_db_id = None
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            p = models.Provider(workspace_id=wsid, secret_id=secret_id, type=body.get('type'), config=body.get('config') or {})
            db.add(p)
            db.commit()
            created_db_id = p.id
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

    _add_audit(wsid, user_id, 'create_provider', object_type='provider', object_id=pid, detail=str(body.get('type')))
    resp = {'id': pid, 'workspace_id': wsid, 'type': body.get('type'), 'secret_id': secret_id}
    if created_db_id:
        resp['db_id'] = created_db_id
    return resp


@app.get('/api/providers')
def list_providers(authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        # require authentication for listing providers
        raise HTTPException(status_code=401)

    wsid = _workspace_for_user(user_id)
    if not wsid:
        raise HTTPException(status_code=400, detail='Workspace not found')

    items = []
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            rows = db.query(models.Provider).filter(models.Provider.workspace_id == wsid).all()
            for r in rows:
                items.append({'id': r.id, 'workspace_id': r.workspace_id, 'type': r.type, 'secret_id': r.secret_id})
            return items
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

    for pid, p in _providers.items():
        if p.get('workspace_id') == wsid:
            items.append({'id': pid, 'workspace_id': p.get('workspace_id'), 'type': p.get('type'), 'secret_id': p.get('secret_id')})
    return items


# --- Missing endpoints expected by the frontend ---
@app.post('/api/auth/register')
def register(body: dict):
    # Minimal register endpoint used by frontend/tests to obtain a token.
    # Create a user and workspace and return a simple token of form 'token-{id}'.
    email = body.get('email')
    password = body.get('password')
    role = body.get('role') or 'user'
    if not email or not password:
        raise HTTPException(status_code=400, detail='email and password required')
    # prefer persisting to DB when available
    created_user_id = None
    hashed = hash_password(password)
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            u = models.User(email=email, hashed_password=hashed, role=role)
            db.add(u)
            db.commit()
            created_user_id = u.id
            # create workspace
            ws = models.Workspace(owner_id=created_user_id, name=f'{email}-workspace')
            db.add(ws)
            db.commit()
            wsid = ws.id
            # mirror in-memory ids where possible
            uid = _next['user']; _next['user'] += 1
            _users[uid] = {'email': email, 'hashed_password': hashed, 'role': role}
            _workspaces[wsid] = {'owner_id': uid, 'name': f'{email}-workspace'}
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

    if not created_user_id:
        # in-memory fallback
        uid = _next['user']; _next['user'] += 1
        _users[uid] = {'email': email, 'hashed_password': hashed, 'role': role}
        wsid = _next['ws']; _next['ws'] += 1
        _workspaces[wsid] = {'owner_id': uid, 'name': f'{email}-workspace'}
        created_user_id = uid

    token = f'token-{created_user_id}'
    return {'access_token': token}


@app.post('/api/auth/login')
def login(body: dict):
    email = body.get('email')
    password = body.get('password')
    if not email or not password:
        raise HTTPException(status_code=400, detail='email and password required')

    # try DB lookup first
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            u = db.query(models.User).filter(models.User.email == email).first()
            if u and verify_password(password, u.hashed_password):
                return {'access_token': f'token-{u.id}'}
            raise HTTPException(status_code=401, detail='invalid credentials')
        finally:
            try:
                db.close()
            except Exception:
                pass

    # in-memory fallback
    for uid, u in _users.items():
        if u.get('email') == email:
            # support both hashed_password and legacy plaintext 'password' if present
            stored_hashed = u.get('hashed_password')
            if stored_hashed:
                if verify_password(password, stored_hashed):
                    return {'access_token': f'token-{uid}'}
            else:
                if u.get('password') == password:
                    return {'access_token': f'token-{uid}'}
            break
    raise HTTPException(status_code=401, detail='invalid credentials')


@app.post('/api/secrets')
def create_secret(body: dict, authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)
    wsid = _workspace_for_user(user_id)
    if not wsid:
        raise HTTPException(status_code=400, detail='Workspace not found')
    name = body.get('name')
    value = body.get('value')
    sid = _next['secret']; _next['secret'] += 1
    _secrets[sid] = {'workspace_id': wsid, 'name': name, 'value': value}
    _add_audit(wsid, user_id, 'create_secret', object_type='secret', object_id=sid, detail=name)
    # attempt to persist
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            s = models.Secret(workspace_id=wsid, name=name, encrypted_value=str(value), created_by=user_id)
            db.add(s)
            db.commit()
            _secrets[sid]['db_id'] = s.id
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
    return {'id': sid}


@app.get('/api/secrets')
def list_secrets(authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        # require authentication for listing secrets
        raise HTTPException(status_code=401)
    wsid = _workspace_for_user(user_id)
    if not wsid:
        raise HTTPException(status_code=400, detail='Workspace not found')
    items = []
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            rows = db.query(models.Secret).filter(models.Secret.workspace_id == wsid).all()
            for r in rows:
                items.append({'id': r.id, 'workspace_id': r.workspace_id, 'name': r.name, 'created_at': r.created_at})
            return items
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

    for sid, s in _secrets.items():
        if s.get('workspace_id') == wsid:
            items.append({'id': sid, 'workspace_id': s.get('workspace_id'), 'name': s.get('name')})
    return items


@app.post('/api/workflows')
def create_workflow(body: dict, authorization: Optional[str] = Header(None)):
    # require authentication for workflow creation
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)

    wsid = _workspace_for_user(user_id)
    if not wsid:
        raise HTTPException(status_code=400, detail='Workspace not found')

    # Basic graph validation similar to tests (keep minimal)
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
            return ({'message': first, 'node_id': node_id}, node_id)
        return None

    # Primitive graph error handling: if graph provided but not dict/list return plain detail
    if 'graph' in body:
        g = body.get('graph')
        if g is not None and not isinstance(g, (dict, list)):
            msg = 'graph must be an object with "nodes" or an array of nodes'
            raise HTTPException(status_code=400, detail=msg)

    v = _validate_graph(body.get('graph'))
    if v is not None:
        detail = v[0]
        if isinstance(detail, dict):
            body_out = dict(detail)
            body_out['detail'] = detail
            return body_out
        else:
            return {'detail': str(detail)}

    # persist workflow
    wid = _next['workflow']; _next['workflow'] += 1
    _workflows[wid] = {'workspace_id': wsid, 'name': body.get('name'), 'description': body.get('description'), 'graph': body.get('graph')}
    # also try to persist to DB
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            w = models.Workflow(workspace_id=wsid, name=body.get('name') or 'Untitled', description=body.get('description'), graph=body.get('graph'))
            db.add(w)
            db.commit()
            _workflows[wid]['db_id'] = w.id
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

    return {'id': wid, 'workspace_id': wsid, 'name': body.get('name')}


@app.get('/api/workflows')
def list_workflows(authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        # require authentication for listing workflows
        raise HTTPException(status_code=401)
    wsid = _workspace_for_user(user_id)
    if not wsid:
        raise HTTPException(status_code=400, detail='Workspace not found')
    items = []
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            rows = db.query(models.Workflow).filter(models.Workflow.workspace_id == wsid).all()
            for r in rows:
                items.append({'id': r.id, 'workspace_id': r.workspace_id, 'name': r.name, 'graph': r.graph})
            return items
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
    for wid, w in _workflows.items():
        if w.get('workspace_id') == wsid:
            items.append({'id': wid, 'workspace_id': w.get('workspace_id'), 'name': w.get('name'), 'graph': w.get('graph')})
    return items


# Scheduler endpoints expected by the frontend
@app.post('/api/scheduler', status_code=201)
def create_scheduler(body: dict, authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)

    wsid = _workspace_for_user(user_id)
    if not wsid:
        raise HTTPException(status_code=400, detail='Workspace not found')

    wid = body.get('workflow_id')
    if not wid:
        raise HTTPException(status_code=400, detail='workflow_id required')

    # ensure workflow belongs to workspace
    wf_ok = False
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            wf = db.query(models.Workflow).filter(models.Workflow.id == wid, models.Workflow.workspace_id == wsid).first()
            if wf:
                wf_ok = True
        except Exception:
            pass
        finally:
            try:
                db.close()
            except Exception:
                pass
    else:
        w = _workflows.get(wid)
        if w and w.get('workspace_id') == wsid:
            wf_ok = True
    if not wf_ok:
        raise HTTPException(status_code=400, detail='workflow not found in workspace')

    sid = _next.get('scheduler', 1)
    _next['scheduler'] = sid + 1
    entry = {'id': sid, 'workspace_id': wsid, 'workflow_id': wid, 'schedule': body.get('schedule'), 'description': body.get('description'), 'active': 1}
    _schedulers[sid] = entry

    _add_audit(wsid, user_id, 'create_scheduler', object_type='scheduler', object_id=sid, detail=str(body.get('description')))
    return {'id': sid, 'workflow_id': wid, 'schedule': body.get('schedule')}


@app.get('/api/scheduler')
def list_scheduler(authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)
    wsid = _workspace_for_user(user_id)
    if not wsid:
        raise HTTPException(status_code=400, detail='Workspace not found')
    items = []
    # prefer DB when available
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            rows = db.query(models.SchedulerEntry).filter(models.SchedulerEntry.workspace_id == wsid).all()
            for r in rows:
                items.append({'id': r.id, 'workspace_id': r.workspace_id, 'workflow_id': r.workflow_id, 'schedule': r.schedule, 'active': r.active, 'last_run_at': r.last_run_at})
            return items
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

    for sid, s in _schedulers.items():
        if s.get('workspace_id') == wsid:
            items.append(s)
    return items


@app.put('/api/scheduler/{sid}')
def update_scheduler(sid: int, body: dict, authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)
    s = _schedulers.get(sid)
    if not s:
        # if DB-backed, attempt to update there (best-effort)
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                row = db.query(models.SchedulerEntry).filter(models.SchedulerEntry.id == sid).first()
                if not row:
                    raise HTTPException(status_code=404)
                if 'schedule' in body:
                    row.schedule = body.get('schedule')
                if 'description' in body:
                    row.description = body.get('description')
                if 'active' in body:
                    row.active = 1 if body.get('active') else 0
                db.add(row)
                db.commit()
                return {'id': row.id, 'workspace_id': row.workspace_id, 'workflow_id': row.workflow_id, 'schedule': row.schedule, 'active': row.active}
            except HTTPException:
                raise
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
        raise HTTPException(status_code=404)
    if 'schedule' in body:
        s['schedule'] = body.get('schedule')
    if 'description' in body:
        s['description'] = body.get('description')
    if 'active' in body:
        s['active'] = 1 if body.get('active') else 0
    return s


@app.delete('/api/scheduler/{sid}')
def delete_scheduler(sid: int, authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)
    if sid not in _schedulers:
        # try DB fallback
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                row = db.query(models.SchedulerEntry).filter(models.SchedulerEntry.id == sid).first()
                if not row:
                    raise HTTPException(status_code=404)
                db.delete(row)
                db.commit()
                return {'status': 'deleted'}
            except HTTPException:
                raise
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
        raise HTTPException(status_code=404)
    del _schedulers[sid]
    return {'status': 'deleted'}
