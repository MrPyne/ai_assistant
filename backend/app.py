# Lightweight compatibility wrappers so tests can run without full FastAPI
try:
    from fastapi import FastAPI, Depends, HTTPException, Request
    from fastapi.security import OAuth2PasswordBearer
    from fastapi.responses import JSONResponse, StreamingResponse
    HAS_FASTAPI = True
except Exception:
    HAS_FASTAPI = False

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

    def Depends(x=None):
        return None

    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class Request:
        async def json(self):
            return {}

    class OAuth2PasswordBearer:
        def __init__(self, tokenUrl=None):
            pass

    class JSONResponse:
        def __init__(self, status_code=200, content=None):
            self.status_code = status_code
            self.content = content

    class StreamingResponse:
        def __init__(self, gen, media_type=None):
            self._gen = gen
            self.media_type = media_type

# Prefer to use passlib when available, otherwise provide a lightweight
# fallback implementation that exposes the same .hash() and .verify()
# methods used by the code and tests.
try:
    from passlib.context import CryptContext
    HAS_PASSLIB = True
except Exception:
    HAS_PASSLIB = False
    import hashlib as _hashlib
    import os as _os
    import binascii as _binascii

    class CryptContext:
        """Minimal pbkdf2_sha256-based fallback compatible with passlib's
        CryptContext.hash() and verify() used in tests.

        Stored hash format: pbkdf2_sha256${iterations}${salt_hex}${dk_hex}
        """
        def __init__(self, schemes=None, deprecated=None):
            self.schemes = schemes or ["pbkdf2_sha256"]
            # Use a reasonably strong default iteration count for tests
            self.iterations = 200000

        def _to_bytes(self, s):
            if isinstance(s, (bytes, bytearray)):
                return bytes(s)
            try:
                return str(s).encode('utf-8')
            except Exception:
                return str(s).encode('utf-8', errors='replace')

        def hash(self, secret):
            b = self._to_bytes(secret)
            salt = _os.urandom(16)
            dk = _hashlib.pbkdf2_hmac('sha256', b, salt, self.iterations)
            return f"pbkdf2_sha256${self.iterations}${_binascii.hexlify(salt).decode()}${_binascii.hexlify(dk).decode()}"

        def verify(self, secret, hashed):
            try:
                parts = hashed.split('$')
                if len(parts) != 4:
                    return False
                algo, iterations, salt_hex, dk_hex = parts
                if algo != 'pbkdf2_sha256':
                    return False
                it = int(iterations)
                salt = _binascii.unhexlify(salt_hex)
                b = self._to_bytes(secret)
                dk = _hashlib.pbkdf2_hmac('sha256', b, salt, it)
                return _binascii.hexlify(dk).decode() == dk_hex
            except Exception:
                return False

from hashlib import sha256
import os
import smtplib
from typing import List, Optional
import asyncio
import json
from datetime import datetime

# SQLAlchemy imports are optional for tests that only use non-DB helpers.
try:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    HAS_SQLALCHEMY = True
except Exception:
    HAS_SQLALCHEMY = False

    def select(*args, **kwargs):
        raise RuntimeError('SQLAlchemy not available in this environment')

    class AsyncSession:
        pass


async def _maybe_await(v):
    if asyncio.iscoroutine(v):
        return await v
    return v


async def db_execute(db, stmt):
    """Execute a statement against either a sync Session or AsyncSession.

    Returns the Result object. Works with both sync and async SQLAlchemy
    sessions by awaiting coroutine results when needed.
    """
    res = db.execute(stmt)
    return await _maybe_await(res)


async def db_add(db, obj):
    r = db.add(obj)
    return await _maybe_await(r)


async def db_commit(db):
    r = db.commit()
    return await _maybe_await(r)


async def db_refresh(db, obj):
    r = db.refresh(obj)
    return await _maybe_await(r)


# Import DB helpers and models (these may import SQLAlchemy; tests that need DB
# functionality will run with proper deps installed in CI/dev environments).
try:
    from backend.database import get_db, AsyncSessionLocal
    from backend.models import RunLog, User, Workspace, Secret, Provider, Workflow, Run
    from backend.crypto import encrypt_value
    from backend.tasks import execute_workflow
except Exception:
    # Provide sensible fallbacks so module-level import doesn't fail when DB
    # related packages aren't installed. Tests that actually need DB will
    # replace these with real implementations via conftest or will use the
    # DummyClient in conftest.
    def get_db():
        raise RuntimeError('Database unavailable')

    class AsyncSessionLocal:
        def __enter__(self):
            raise RuntimeError('Database unavailable')

    class RunLog:
        pass

    class User:
        pass

    class Workspace:
        pass

    class Secret:
        pass

    class Provider:
        pass

    class Workflow:
        pass

    class Run:
        pass

    def encrypt_value(v):
        return v

    def execute_workflow():
        class Dummy:
            def delay(self, *a, **k):
                raise RuntimeError('Celery not available')
        return Dummy()

app = FastAPI()

# Auth helpers
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
# Prefer a hashing scheme without bcrypt's 72-byte input limit for development
# environments where the bcrypt_sha256 handler might not be available. We
# include a fallback ordering so environments with pure-Python handlers work
# reliably (pbkdf2_sha256) while still allowing bcrypt variants if present.
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt_sha256", "bcrypt"], deprecated="auto")


def _maybe_prehash_for_bcrypt(pw: str) -> str:
    """Return a value safe to pass to bcrypt when the input may be longer
    than bcrypt's 72 byte limit.

    Behaviour:
    - If pw is bytes, decode as UTF-8 (fall back to latin-1) so we operate
      on a str.
    - If the UTF-8 encoded password is longer than 72 bytes we replace it
      with its SHA256 hex digest (a 64-char ASCII string). This mirrors the
      behaviour of bcrypt_sha256 while staying explicit and working even if
      the handler isn't available in the environment.

    Always return a str (never bytes) so passlib/bcrypt backends receive a
    consistent input. We encode with 'utf-8' and use 'replace' on errors to
    ensure deterministic behaviour for arbitrary input types.
    """
    # If bytes/bytearray were passed, decode to str first (utf-8 with latin-1 fallback)
    if isinstance(pw, (bytes, bytearray)):
        try:
            pw = pw.decode('utf-8')
        except Exception:
            pw = pw.decode('latin-1')

    # Ensure we have a string representation for non-str inputs
    if not isinstance(pw, str):
        pw = str(pw)

    # Compute UTF-8 bytes length robustly (replace invalid sequences deterministically)
    b = pw.encode('utf-8', errors='replace')

    if len(b) > 72:
        # use hex digest so it's ASCII and deterministic
        return sha256(b).hexdigest()
    return pw


def hash_password(pw: str) -> str:
    """Hash password with passlib, pre-hashing long inputs to avoid
    bcrypt's 72-byte limit.

    Always pre-hash long values (and return hashed value). This ensures we
    never pass inputs longer than 72 bytes into bcrypt. We use the
    _maybe_prehash_for_bcrypt helper which returns either the original string
    (if <=72 bytes when UTF-8 encoded) or a SHA256 hex digest (64 ASCII
    characters) which is safe for bcrypt. If the underlying passlib handler
    still raises a ValueError (e.g., unexpected bcrypt handler without the
    sha256 wrapper), we explicitly compute a SHA256 hex digest of the raw
    input and hash that. This guarantees we never pass >72 bytes into bcrypt
    backends.
    """
    # Normalize and pre-hash long values so we never pass more than 72
    # bytes into bcrypt handlers in normal operation.
    safe_pw = _maybe_prehash_for_bcrypt(pw)
    try:
        return pwd_context.hash(safe_pw)
    except ValueError:
        # Underlying handler refused the input despite our pre-hash. Compute
        # a deterministic SHA256 hex digest of the original input and hash
        # that instead.
        if isinstance(pw, (bytes, bytearray)):
            b = pw
        else:
            try:
                b = str(pw).encode('utf-8')
            except Exception:
                b = str(pw).encode('utf-8', errors='replace')
        pre = sha256(b).hexdigest()
        return pwd_context.hash(pre)


def verify_password(plain_pw: str, hashed: str) -> bool:
    """Verify password against stored hash. Mirrors the same pre-hash
    behaviour used when creating the hash so verification succeeds for
    long passwords.
    """
    # First try straightforward verification. Some bcrypt handlers may
    # raise ValueError when passed input longer than 72 bytes; handle that
    # and also handle the common case where verify() simply returns False
    # (e.g., our pbkdf2 fallback).
    try:
        ok = pwd_context.verify(plain_pw, hashed)
        if ok:
            return True
    except ValueError:
        # fall through to pre-hash attempt
        pass

    # Attempt verification using the pre-hashed (sha256 hex) form which
    # matches how we create hashes for long passwords.
    try:
        safe_pw = _maybe_prehash_for_bcrypt(plain_pw)
        return pwd_context.verify(safe_pw, hashed)
    except Exception:
        # Any remaining errors or mismatches mean verification failed.
        return False


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Return the currently authenticated user based on the provided OAuth2
    token. Accepts a simple development token format of 'token-<user_id>'.

    Behaviour:
    - If SQLAlchemy/db is available, attempt to load the User from the DB.
    - If DB is not available (tests/dev fallback), return a lightweight
      User-like object with an 'id' attribute so endpoints that expect user.id
      continue to work.
    """
    if not token:
        raise HTTPException(status_code=401, detail='Not authenticated')

    # Expect the simplistic dev token format used by the app (token-<id>)
    if token.startswith('token-'):
        try:
            uid = int(token.split('-', 1)[1])
        except Exception:
            raise HTTPException(status_code=401, detail='Invalid token')

        if HAS_SQLALCHEMY:
            try:
                res = await db_execute(db, select(User).filter(User.id == uid))
                user = res.scalars().first()
                if not user:
                    raise HTTPException(status_code=401, detail='User not found')
                return user
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=401, detail='Invalid token')
        else:
            # Return a minimal User-like object for environments without DB.
            u = User()
            try:
                setattr(u, 'id', uid)
            except Exception:
                # Fallback to attribute assignment via __dict__ if needed
                try:
                    u.__dict__['id'] = uid
                except Exception:
                    pass
            return u

    raise HTTPException(status_code=401, detail='Invalid token')


# The rest of the module provides HTTP endpoints. These functions use the
# SQLAlchemy 'select' helper and DB session; if SQLAlchemy isn't available
# tests that need DB will not run in this environment. We keep function
# definitions so importing this module in tests that only need helpers
# (e.g., password hashing) won't fail.

if HAS_SQLALCHEMY:
    @app.get('/api/runs/{run_id}/logs')
    async def get_run_logs(run_id: int, db: AsyncSession = Depends(get_db)):
        """Return run logs (redacted) for a given run id.

        This queries the DB for RunLog entries and returns them as a list of
        dicts sorted by timestamp. The DB session is provided by the get_db
        dependency which ensures proper closing.
        """
        try:
            res = await db_execute(db, select(RunLog).filter(RunLog.run_id == run_id).order_by(RunLog.timestamp.asc()))
            rows = res.scalars().all()
            out = []
            for r in rows:
                out.append({
                    'id': r.id,
                    'node_id': r.node_id,
                    'timestamp': r.timestamp.isoformat() if r.timestamp else None,
                    'level': r.level,
                    'message': r.message,
                })
            return JSONResponse(status_code=200, content={'logs': out})
        except Exception:
            raise HTTPException(status_code=500, detail='Failed to fetch run logs')


    @app.get('/api/runs/{run_id}/stream')
    async def stream_run_logs(run_id: int, request: Request, user: User = Depends(get_current_user)):
        """Stream RunLog entries as Server-Sent Events (SSE).

        This endpoint polls the database for new RunLog rows and pushes them to
        connected clients. It is intentionally simple and suitable for local
        development. In production we would use a push-based system.
        """

        def format_sse(data: dict):
            return f"data: {json.dumps(data)}\n\n"

        # We open a dedicated AsyncSession here and keep it open for the duration
        # of the streaming response. Using the dependency would close the session
        # too early because dependency cleanup happens when the endpoint returns.
        async def event_generator():
            last_id = 0
            async with AsyncSessionLocal() as db:
                try:
                    res = await db_execute(db, select(RunLog).filter(RunLog.run_id == run_id).order_by(RunLog.id.asc()))
                    rows = res.scalars().all()
                    last_id = rows[-1].id if rows else 0
                except Exception:
                    last_id = 0

                # send any existing logs first
                try:
                    res = await db_execute(db, select(RunLog).filter(RunLog.run_id == run_id, RunLog.id > 0).order_by(RunLog.id.asc()))
                    existing = res.scalars().all()
                    for r in existing:
                        payload = {'id': r.id, 'node_id': r.node_id, 'timestamp': r.timestamp.isoformat() if r.timestamp else None, 'level': r.level, 'message': r.message}
                        yield format_sse(payload)
                        last_id = max(last_id, r.id)
                except Exception:
                    # ignore errors while trying to read initial logs
                    pass

                # Poll for new logs until client disconnects or run finishes
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        res = await db_execute(db, select(RunLog).filter(RunLog.run_id == run_id, RunLog.id > last_id).order_by(RunLog.id.asc()))
                        new = res.scalars().all()
                        if new:
                            for r in new:
                                payload = {'id': r.id, 'node_id': r.node_id, 'timestamp': r.timestamp.isoformat() if r.timestamp else None, 'level': r.level, 'message': r.message}
                                yield format_sse(payload)
                                last_id = max(last_id, r.id)
                        else:
                            # check if run is finished; if so and no new logs, close stream
                            res2 = await db_execute(db, select(Run).filter(Run.id == run_id))
                            run = res2.scalars().first()
                            if run and run.finished_at is not None:
                                break
                    except Exception:
                        # ignore DB errors transiently
                        pass
                    await asyncio.sleep(1)

        return StreamingResponse(event_generator(), media_type='text/event-stream')


    @app.get("/ping")
    async def ping():
        return {"status": "ok"}


    def send_email(to_email: str, subject: str, body: str):
        """Simple SMTP send helper used by the auth resend flow.

        This is intentionally small for the MVP — tests can mock smtplib.SMTP to
        validate behaviour without sending real email.
        """
        smtp_host = os.getenv('SMTP_HOST', 'localhost')
        smtp_port = int(os.getenv('SMTP_PORT', 25))
        from_email = os.getenv('SMTP_FROM', 'noreply@example.com')
        # Use context manager so tests can patch smtplib.SMTP easily
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.sendmail(from_email, [to_email], f"Subject: {subject}\n\n{body}")


    @app.post('/api/auth/resend')
    async def resend_email_endpoint(data: dict, db: AsyncSession = Depends(get_db)):
        """Resend a user-facing email (e.g., verification or magic link).

        For security, this endpoint returns 200 even if the user/email does not
        exist to avoid user enumeration. The actual send is attempted only when
        the user is present. Tests can mock smtplib.SMTP to assert behaviour.
        """
        email = data.get('email')
        if not email:
            raise HTTPException(status_code=400, detail='email required')
        res = await db_execute(db, select(User).filter(User.email == email))
        user = res.scalars().first()
        # Do not reveal whether the user exists
        if not user:
            return {"status": "ok"}
        try:
            # In a real app we'd generate a token / link. Keep simple for MVP.
            send_email(email, 'Resend', 'Here is your requested email')
            return {"status": "ok"}
        except Exception:
            raise HTTPException(status_code=500, detail='Failed to send email')


    @app.post('/api/auth/register')
    async def register(data: dict, db: AsyncSession = Depends(get_db)):
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            raise HTTPException(status_code=400, detail='email and password required')
        res = await db_execute(db, select(User).filter(User.email == email))
        existing = res.scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail='user already exists')
        hashed = hash_password(password)
        user = User(email=email, hashed_password=hashed)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        # create a default workspace for the user
        ws = Workspace(name=f"{email}-workspace", owner_id=user.id)
        db.add(ws)
        await db.commit()
        # simple token for dev use
        token = f"token-{user.id}"
        return {"access_token": token}


    @app.post('/api/auth/login')
    async def login(data: dict, db: AsyncSession = Depends(get_db)):
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            raise HTTPException(status_code=400, detail='email and password required')
        res = await db_execute(db, select(User).filter(User.email == email))
        user = res.scalars().first()
        if not user:
            raise HTTPException(status_code=400, detail='invalid credentials')
        if not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=400, detail='invalid credentials')
        token = f"token-{user.id}"
        return {"access_token": token}


    @app.post('/api/secrets')
    async def create_secret(data: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
        name = data.get('name')
        value = data.get('value')
        if not name or value is None:
            raise HTTPException(status_code=400, detail='name and value required')
        # find user's workspace
        res = await db_execute(db, select(Workspace).filter(Workspace.owner_id == user.id))
        ws = res.scalars().first()
        if not ws:
            raise HTTPException(status_code=400, detail='workspace not found')
        enc = encrypt_value(value)
        s = Secret(workspace_id=ws.id, name=name, encrypted_value=enc, created_by=user.id)
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return {"id": s.id}


    @app.get('/api/secrets')
    async def list_secrets(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
        res = await db_execute(db, select(Workspace).filter(Workspace.owner_id == user.id))
        ws = res.scalars().first()
        if not ws:
            return []
        res2 = await db_execute(db, select(Secret).filter(Secret.workspace_id == ws.id))
        rows = res2.scalars().all()
        out = []
        for r in rows:
            out.append({"id": r.id, "workspace_id": r.workspace_id, "name": r.name, "created_by": r.created_by, "created_at": r.created_at.isoformat() if r.created_at else None})
        return out


    @app.post('/api/providers')
    async def create_provider(data: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
        ptype = data.get('type')
        config = data.get('config') or {}
        secret_id = data.get('secret_id')
        if not ptype:
            raise HTTPException(status_code=400, detail='type required')
        res = await db_execute(db, select(Workspace).filter(Workspace.owner_id == user.id))
        ws = res.scalars().first()
        if not ws:
            raise HTTPException(status_code=400, detail='workspace not found')
        # validate secret belongs to workspace if provided
        if secret_id:
            res3 = await db_execute(db, select(Secret).filter(Secret.id == secret_id, Secret.workspace_id == ws.id))
            s = res3.scalars().first()
            if not s:
                raise HTTPException(status_code=400, detail='secret_id not found in workspace')
        prov = Provider(workspace_id=ws.id, type=ptype, secret_id=secret_id, config=config)
        db.add(prov)
        await db.commit()
        await db.refresh(prov)
        # Do not return provider.config to avoid leaking secrets; tests expect minimal response
        return {"id": prov.id, "workspace_id": prov.workspace_id, "type": prov.type, "secret_id": prov.secret_id}

    @app.get('/api/providers')
    async def list_providers(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
        res = await db_execute(db, select(Workspace).filter(Workspace.owner_id == user.id))
        ws = res.scalars().first()
        if not ws:
            return []
        res2 = await db_execute(db, select(Provider).filter(Provider.workspace_id == ws.id))
        rows = res2.scalars().all()
        out = []
        for r in rows:
            out.append({"id": r.id, "workspace_id": r.workspace_id, "type": r.type, "secret_id": r.secret_id, "created_at": r.created_at.isoformat() if r.created_at else None})
        return out


    @app.post('/api/workflows')
    async def create_workflow(data: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
        name = data.get('name') or 'Untitled'
        description = data.get('description')
        graph = data.get('graph')
        res = await db_execute(db, select(Workspace).filter(Workspace.owner_id == user.id))
        ws = res.scalars().first()
        if not ws:
            raise HTTPException(status_code=400, detail='workspace not found')
        wf = Workflow(workspace_id=ws.id, name=name, description=description, graph=graph)
        db.add(wf)
        await db.commit()
        await db.refresh(wf)
        return {"id": wf.id, "workspace_id": wf.workspace_id, "name": wf.name}

    @app.get('/api/workflows')
    async def list_workflows(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
        res = await db_execute(db, select(Workspace).filter(Workspace.owner_id == user.id))
        ws = res.scalars().first()
        if not ws:
            return []
        res2 = await db_execute(db, select(Workflow).filter(Workflow.workspace_id == ws.id))
        rows = res2.scalars().all()
        out = []
        for r in rows:
            out.append({"id": r.id, "workspace_id": r.workspace_id, "name": r.name, "description": r.description, "graph": r.graph, "version": r.version})
        return out


    @app.post('/api/webhook/{workflow_id}/{trigger_id}')
    async def webhook_trigger(workflow_id: int, trigger_id: str, request: Request, db: AsyncSession = Depends(get_db)):
        """Webhook trigger that creates a Run and enqueues processing.

        Returns run_id and queued status. The actual processing is performed by
        the worker (Celery task) which may not be running in test environments.
        """
        payload = None
        try:
            payload = await request.json()
        except Exception:
            try:
                body = await request.body()
                payload = body.decode() if body else None
            except Exception:
                payload = None
        # ensure workflow exists
        res = await db_execute(db, select(Workflow).filter(Workflow.id == workflow_id))
        wf = res.scalars().first()
        if not wf:
            raise HTTPException(status_code=404, detail='workflow not found')
        run = Run(workflow_id=workflow_id, status='queued', input_payload=payload, started_at=datetime.utcnow())
        db.add(run)
        await db.commit()
        await db.refresh(run)
        # enqueue Celery task (best-effort)
        try:
            execute_workflow.delay(run.id)
        except Exception:
            # ignore if Celery not available in this environment
            pass
        return {"run_id": run.id, "status": "queued"}


    @app.get('/api/workflows/{workflow_id}/runs')
    async def list_runs_for_workflow(
        workflow_id: int,
        limit: int = 50,
        offset: int = 0,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ):
        """Return runs for a specific workflow (owned by current user).

        This ensures the workflow belongs to the requesting user's workspace
        and returns a paginated list of runs ordered by newest first.
        """
        # sanitize pagination params
        try:
            limit = int(limit)
        except Exception:
            limit = 50
        try:
            offset = int(offset)
        except Exception:
            offset = 0
        # enforce reasonable limits
        if limit <= 0:
            limit = 1
        if limit > 100:
            limit = 100
        if offset < 0:
            offset = 0

        # ensure workflow exists and belongs to user's workspace
        res = await db_execute(db, select(Workflow).filter(Workflow.id == workflow_id))
        wf = res.scalars().first()
        if not wf:
            raise HTTPException(status_code=404, detail='workflow not found')

        # fetch user's workspace
        res2 = await db_execute(db, select(Workspace).filter(Workspace.owner_id == user.id))
        ws = res2.scalars().first()
        if not ws or wf.workspace_id != ws.id:
            # hide existence of workflow if not accessible
            raise HTTPException(status_code=404, detail='workflow not found')

        stmt = select(Run).filter(Run.workflow_id == workflow_id).order_by(Run.id.desc()).limit(limit).offset(offset)
        res3 = await db_execute(db, stmt)
        rows = res3.scalars().all()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "workflow_id": r.workflow_id,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            })
        return out

    @app.post('/api/workflows/{workflow_id}/run')
    async def run_workflow(workflow_id: int, data: dict = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
        res = await db_execute(db, select(Workflow).filter(Workflow.id == workflow_id))
        wf = res.scalars().first()
        if not wf:
            raise HTTPException(status_code=404, detail='workflow not found')
        payload = data or {}
        run = Run(workflow_id=workflow_id, status='queued', input_payload=payload, started_at=datetime.utcnow())
        db.add(run)
        await db.commit()
        await db.refresh(run)
        try:
            execute_workflow.delay(run.id)
        except Exception:
            pass
        return {"run_id": run.id, "status": "queued"}

    @app.get('/api/runs')
    async def list_runs(
        workflow_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ):
        """List runs across workflows or filter by workflow_id. Supports pagination via limit/offset.
        """
        # sanitize pagination params
        try:
            limit = int(limit)
        except Exception:
            limit = 50
        try:
            offset = int(offset)
        except Exception:
            offset = 0
        if limit <= 0:
            limit = 1
        if limit > 100:
            limit = 100
        if offset < 0:
            offset = 0

        # Ensure we only return runs the user is permitted to see. When a
        # workflow_id is provided, verify the workflow belongs to the user's
        # workspace. When no workflow_id is provided, restrict results to runs
        # that belong to workflows in the user's workspace.
        # fetch user's workspace
        res_ws = await db_execute(db, select(Workspace).filter(Workspace.owner_id == user.id))
        ws = res_ws.scalars().first()
        if not ws:
            return []

        if workflow_id:
            # ensure workflow exists and belongs to user's workspace
            res_wf = await db_execute(db, select(Workflow).filter(Workflow.id == workflow_id))
            wf = res_wf.scalars().first()
            if not wf or wf.workspace_id != ws.id:
                # hide existence of workflow if not accessible
                raise HTTPException(status_code=404, detail='workflow not found')
            stmt = select(Run).filter(Run.workflow_id == workflow_id).order_by(Run.id.desc()).limit(limit).offset(offset)
        else:
            # restrict to workflows in this workspace to avoid cross-workspace leakage
            stmt = select(Run).join(Workflow).filter(Workflow.workspace_id == ws.id).order_by(Run.id.desc()).limit(limit).offset(offset)
        res = await db_execute(db, stmt)
        rows = res.scalars().all()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "workflow_id": r.workflow_id,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            })
        return out


    @app.get('/api/runs/{run_id}')
    async def get_run(run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
        """Return a single run's metadata and (optionally) its logs.

        This endpoint is useful for run history views where the frontend
        needs details about a specific run. Logs are returned as an array of
        simple objects (id, node_id, timestamp, level, message).
        """
        try:
            res = await db_execute(db, select(Run).filter(Run.id == run_id))
            run = res.scalars().first()
            if not run:
                raise HTTPException(status_code=404, detail='run not found')

            # fetch associated logs (may be empty)
            res2 = await db_execute(db, select(RunLog).filter(RunLog.run_id == run_id).order_by(RunLog.id.asc()))
            rows = res2.scalars().all()
            logs_out = []
            for r in rows:
                logs_out.append({
                    'id': r.id,
                    'node_id': r.node_id,
                    'timestamp': r.timestamp.isoformat() if r.timestamp else None,
                    'level': r.level,
                    'message': r.message,
                })

            return {
                'id': run.id,
                'workflow_id': run.workflow_id,
                'status': run.status,
                'input_payload': run.input_payload,
                'output_payload': run.output_payload,
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'finished_at': run.finished_at.isoformat() if run.finished_at else None,
                'attempts': getattr(run, 'attempts', 0),
                'logs': logs_out,
            }
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=500, detail='Failed to fetch run')
