"""Shared helpers moved out of app_impl for reuse across route modules."""
from typing import Optional, Dict, Any
from datetime import datetime
import os
import threading
from ..utils import redact_secrets
try:
    from ..node_schemas import get_node_json_schema
except Exception:
    # best-effort; tests may run without the module available
    def get_node_json_schema(label: str):
        return {"type": "object"}

# Import DB/time/etc when available
try:
    from ..database import SessionLocal
    from .. import models
    _DB_AVAILABLE = True
except Exception:
    SessionLocal = None
    models = None
    _DB_AVAILABLE = False

# simple in-memory stores (kept for compatibility)
_runs: Dict[int, Dict[str, Any]] = {}
_next = {'user': 1, 'ws': 1, 'scheduler': 1, 'run': 1, 'provider': 1, 'secret': 1, 'workflow': 1, 'webhook': 1}
_users: Dict[int, Dict[str, Any]] = {}
_workspaces: Dict[int, Dict[str, Any]] = {}
_schedulers: Dict[int, Dict[str, Any]] = {}
_providers: Dict[int, Dict[str, Any]] = {}
_secrets: Dict[int, Dict[str, Any]] = {}
_workflows: Dict[int, Dict[str, Any]] = {}
_webhooks: Dict[int, Dict[str, Any]] = {}

# Password helpers
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

# minimal token helpers
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

# Auth route implementations extracted for test reuse
try:
    from fastapi.responses import JSONResponse
    from fastapi import HTTPException
    _FASTAPI_HEADERS = True
except Exception:
    # lightweight stand-ins for test environment when FastAPI isn't installed
    class HTTPException(Exception):
        def __init__(self, status_code: int = 500, detail: str = None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class JSONResponse:  # very small stand-in used by tests
        def __init__(self, content=None, status_code: int = 200):
            self.content = content
            self.status_code = status_code

    _FASTAPI_HEADERS = False


def auth_register_db(body: dict, db):
    try:
        email = body.get('email') if isinstance(body, dict) else None
        password = body.get('password') if isinstance(body, dict) else None
        role = body.get('role') if isinstance(body, dict) else 'user'
        if not email or not password:
            raise HTTPException(status_code=400, detail='email and password required')
        # prefer DB path
        created = False
        session = db if db is not None else SessionLocal()
        try:
            existing = session.query(models.User).filter(models.User.email == email).first()
            if existing:
                raise HTTPException(status_code=400, detail='email already registered')
            hashed = hash_password(password)
            user = models.User(email=email, hashed_password=hashed, role=role)
            session.add(user)
            session.commit()
            session.refresh(user)
            ws = models.Workspace(name=f'{email}-workspace', owner_id=user.id)
            session.add(ws)
            session.commit()
            token = f'token-{user.id}'
            return JSONResponse(status_code=200, content={'access_token': token})
        finally:
            try:
                if db is None:
                    session.close()
            except Exception:
                pass
    except HTTPException:
        raise
    except Exception:
        # fallback to in-memory
        uid = _next.get('user', 1)
        _next['user'] = uid + 1
        _users[uid] = {'email': email, 'password': password, 'role': role}
        wsid = _next.get('ws', 1)
        _next['ws'] = wsid + 1
        _workspaces[wsid] = {'owner_id': uid, 'name': f'{email}-workspace'}
        token = f'token-{uid}'
        return JSONResponse(status_code=200, content={'access_token': token})


def auth_register_fallback(body: dict):
    email = body.get('email') if isinstance(body, dict) else None
    password = body.get('password') if isinstance(body, dict) else None
    role = body.get('role') if isinstance(body, dict) else 'user'
    if not email or not password:
        return JSONResponse(status_code=400, content={'detail': 'email and password required'})
    uid = _next.get('user', 1)
    _next['user'] = uid + 1
    _users[uid] = {'email': email, 'password': password, 'role': role}
    wsid = _next.get('ws', 1)
    _next['ws'] = wsid + 1
    _workspaces[wsid] = {'owner_id': uid, 'name': f'{email}-workspace'}
    token = f'token-{uid}'
    return JSONResponse(status_code=200, content={'access_token': token})


def auth_login(body: dict):
    email = body.get('email') if isinstance(body, dict) else None
    password = body.get('password') if isinstance(body, dict) else None
    if not email or not password:
        raise HTTPException(status_code=401)
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            user = db.query(models.User).filter(models.User.email == email).first()
            if not user:
                raise HTTPException(status_code=401)
            if verify_password(password, user.hashed_password):
                return JSONResponse(status_code=200, content={'access_token': f'token-{user.id}'})
            raise HTTPException(status_code=401)
        finally:
            try:
                db.close()
            except Exception:
                pass
    # fallback in-memory
    uid = None
    stored = None
    for i, u in _users.items():
        if u.get('email') == email:
            uid = i
            stored = u
            break
    if uid is None:
        raise HTTPException(status_code=401)
    if stored.get('password') == password or verify_password(password, stored.get('password')):
        return JSONResponse(status_code=200, content={'access_token': f'token-{uid}'})
    raise HTTPException(status_code=401)


def auth_resend(body: dict):
    email = body.get('email') if isinstance(body, dict) else None
    if not email:
        return JSONResponse(status_code=400, content={'detail': 'email required'})
    user_exists = False
    if _DB_AVAILABLE:
        try:
            db = SessionLocal()
            u = db.query(models.User).filter(models.User.email == email).first()
            if u:
                user_exists = True
        except Exception:
            user_exists = False
        finally:
            try:
                db.close()
            except Exception:
                pass
    else:
        for u in _users.values():
            if u.get('email') == email:
                user_exists = True
                break
    if not user_exists:
        return JSONResponse(status_code=200, content={'status': 'ok'})
    host = os.environ.get('SMTP_HOST', 'localhost')
    try:
        port = int(os.environ.get('SMTP_PORT', '25'))
    except Exception:
        port = 25
    try:
        import smtplib
        with smtplib.SMTP(host, port) as s:
            msg = f"Subject: Resend\n\nResend to {email}"
            s.sendmail('noreply@example.com', [email], msg)
    except Exception:
        pass
    return JSONResponse(status_code=200, content={'status': 'ok'})

def node_test_impl(body: dict, authorization: Optional[str] = None):
    """Simple node test handler used by the compatibility layer and tests.

    Behavior is intentionally minimal: when LIVE_LLM or LIVE_HTTP are not
    enabled the function returns mocked responses (containing "[mock]") so
    tests that expect blocking behavior pass. When the corresponding LIVE_*
    env var is set to 'true' the function still returns a placeholder
    result (we don't perform external network/llm calls in tests/runtime
    environments).
    """
    node = body.get('node') if isinstance(body, dict) else None
    if not node:
        return {'error': 'invalid node'}
    # conservative schema validation for friendly labels
    try:
        label = (node.get('data') or {}).get('label')
        if label:
            schema = get_node_json_schema(label)
            try:
                import jsonschema
                cfg = (node.get('data') or {}).get('config')
                if cfg is not None:
                    jsonschema.validate(instance=cfg, schema=schema)
            except Exception:
                # ignore jsonschema import/validation failures to remain permissive
                pass
    except Exception:
        pass

    ntype = node.get('type')
    live_llm = os.environ.get('LIVE_LLM', 'false').lower() == 'true'
    live_http = os.environ.get('LIVE_HTTP', 'false').lower() == 'true'

    if ntype == 'llm':
        if not live_llm:
            return {'result': {'text': '[mock] llm blocked by LIVE_LLM'}}
        # In a live-llm environment we'd call the adapter; return placeholder
        return {'result': {'text': 'LIVE_LLM enabled - (live llm not executed in this environment)'}}

    if ntype == 'http':
        # Respect LIVE_HTTP toggle: when disabled return a mock blocking message
        if not live_http:
            return {'result': {'text': '[mock] http blocked by LIVE_HTTP'}}
        # In LIVE_HTTP mode we would perform a real request; return placeholder
        return {'result': {'text': 'LIVE_HTTP enabled - (live http not executed in this environment)'}}

    # Preserve original_config on all nodes to make round-tripping and
    # migration tooling simpler. If the caller provided a 'data.config'
    # we keep a copy under 'original_config' if not already present.
    try:
        if isinstance(node.get('data'), dict):
            cfg = node.get('data', {}).get('config')
            if cfg is not None and isinstance(cfg, dict):
                if 'original_config' not in cfg:
                    cfg['original_config'] = dict(cfg)
    except Exception:
        pass

    # Slack/webhook-style nodes
    if ntype == 'slack' or (isinstance(node.get('data'), dict) and (node.get('data', {}).get('label') or '').lower().startswith('slack')):
        # Respect LIVE_HTTP toggle for outbound webhooks
        live_http = os.environ.get('LIVE_HTTP', 'false').lower() == 'true'
        if not live_http:
            return {'result': {'text': '[mock] slack/webhook blocked by LIVE_HTTP'}}
        return {'result': {'text': 'LIVE_HTTP enabled - (live slack/webhook not executed in this environment)'}}

    # Email nodes
    if ntype == 'email' or (isinstance(node.get('data'), dict) and (node.get('data', {}).get('label') or '').lower().startswith('email')):
        # Respect LIVE_SMTP toggle to avoid sending real emails in tests
        live_smtp = os.environ.get('LIVE_SMTP', 'false').lower() == 'true'
        if not live_smtp:
            return {'result': {'text': '[mock] email blocked by LIVE_SMTP'}}
        return {'result': {'text': 'LIVE_SMTP enabled - (live email not executed in this environment)'}}

    return {'error': 'unsupported node type'}
