"""Shared helpers moved out of app_impl for reuse across route modules."""
from typing import Optional, Dict, Any
from datetime import datetime
import os
import threading
from ..utils import redact_secrets

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
from fastapi.responses import JSONResponse
from fastapi import HTTPException

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
