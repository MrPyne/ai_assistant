from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
import os
import smtplib
from typing import List, Optional
from fastapi.responses import JSONResponse, StreamingResponse
import asyncio
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio


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


from backend.database import get_db, AsyncSessionLocal
from backend.models import RunLog, User, Workspace, Secret, Provider, Workflow, Run
from backend.crypto import encrypt_value

from backend.tasks import execute_workflow

app = FastAPI()

# Auth helpers
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    """Resolve the current user from Authorization header or query param.

    Dev-friendly behaviour:
    - If Authorization: Bearer token-{id} is provided, resolve that user by id.
    - If ?access_token=token-{id} is provided (used by EventSource in the UI), resolve that user.
    - If no token provided, fall back to the first user in the DB (convenience for local dev).

    In production this should be replaced with a real token-validation flow.
    """
    auth = None
    # Prefer header
    auth = request.headers.get('Authorization')
    if not auth:
        # allow access_token query param (EventSource can't set headers)
        auth = request.query_params.get('access_token')

    if auth:
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1]
        else:
            token = auth
        # token format is token-{user_id} in this dev stub
        if isinstance(token, str) and token.startswith('token-'):
            try:
                uid = int(token.split('-', 1)[1])
                res = await db_execute(db, select(User).filter(User.id == uid))
                user = res.scalars().first()
                if user:
                    return user
            except Exception:
                # fall through to fallback behaviour
                pass

    # Fallback: return first user (convenient for local development)
    res = await db_execute(db, select(User))
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    return user


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
    hashed = pwd_context.hash(password)
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
    if not pwd_context.verify(password, user.hashed_password):
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
async def list_runs(workflow_id: Optional[int] = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if workflow_id:
        res = await db_execute(db, select(Run).filter(Run.workflow_id == workflow_id).order_by(Run.id.desc()))
    else:
        res = await db_execute(db, select(Run).order_by(Run.id.desc()))
    rows = res.scalars().all()
    out = []
    for r in rows:
        out.append({"id": r.id, "workflow_id": r.workflow_id, "status": r.status, "started_at": r.started_at.isoformat() if r.started_at else None, "finished_at": r.finished_at.isoformat() if r.finished_at else None})
    return out
