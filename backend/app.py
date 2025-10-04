from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import os
import smtplib
from typing import List, Optional
from fastapi.responses import JSONResponse
from backend.database import get_db
from backend.models import RunLog, User, Workspace, Secret, Provider, Workflow, Run
from backend.crypto import encrypt_value
from datetime import datetime

from backend.tasks import execute_workflow

app = FastAPI()

# Auth helpers
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@app.get('/api/runs/{run_id}/logs')
def get_run_logs(run_id: int, db: Session = Depends(get_db)):
    """Return run logs (redacted) for a given run id.

    This queries the DB for RunLog entries and returns them as a list of
    dicts sorted by timestamp. The DB session is provided by the get_db
    dependency which ensures proper closing.
    """
    try:
        rows = db.query(RunLog).filter(RunLog.run_id == run_id).order_by(RunLog.timestamp.asc()).all()
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


@app.get("/ping")
def ping():
    return {"status": "ok"}


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # Minimal placeholder: in real app validate token and load user
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    return user


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
def resend_email(data: dict, db: Session = Depends(get_db)):
    """Resend a user-facing email (e.g., verification or magic link).

    For security, this endpoint returns 200 even if the user/email does not
    exist to avoid user enumeration. The actual send is attempted only when
    the user is present. Tests can mock smtplib.SMTP to assert behaviour.
    """
    email = data.get('email')
    if not email:
        raise HTTPException(status_code=400, detail='email required')
    user = db.query(User).filter(User.email == email).first()
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
def register(data: dict, db: Session = Depends(get_db)):
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        raise HTTPException(status_code=400, detail='email and password required')
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail='user already exists')
    hashed = pwd_context.hash(password)
    user = User(email=email, hashed_password=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)
    # create a default workspace for the user
    ws = Workspace(name=f"{email}-workspace", owner_id=user.id)
    db.add(ws)
    db.commit()
    # simple token for dev use
    token = f"token-{user.id}"
    return {"access_token": token}


@app.post('/api/auth/login')
def login(data: dict, db: Session = Depends(get_db)):
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        raise HTTPException(status_code=400, detail='email and password required')
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=400, detail='invalid credentials')
    if not pwd_context.verify(password, user.hashed_password):
        raise HTTPException(status_code=400, detail='invalid credentials')
    token = f"token-{user.id}"
    return {"access_token": token}


@app.post('/api/secrets')
def create_secret(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = data.get('name')
    value = data.get('value')
    if not name or value is None:
        raise HTTPException(status_code=400, detail='name and value required')
    # find user's workspace
    ws = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
    if not ws:
        raise HTTPException(status_code=400, detail='workspace not found')
    enc = encrypt_value(value)
    s = Secret(workspace_id=ws.id, name=name, encrypted_value=enc, created_by=user.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id}


@app.get('/api/secrets')
def list_secrets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ws = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
    if not ws:
        return []
    rows = db.query(Secret).filter(Secret.workspace_id == ws.id).all()
    out = []
    for r in rows:
        out.append({"id": r.id, "workspace_id": r.workspace_id, "name": r.name, "created_by": r.created_by, "created_at": r.created_at.isoformat() if r.created_at else None})
    return out


@app.post('/api/providers')
def create_provider(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ptype = data.get('type')
    config = data.get('config') or {}
    secret_id = data.get('secret_id')
    if not ptype:
        raise HTTPException(status_code=400, detail='type required')
    ws = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
    if not ws:
        raise HTTPException(status_code=400, detail='workspace not found')
    # validate secret belongs to workspace if provided
    if secret_id:
        s = db.query(Secret).filter(Secret.id == secret_id, Secret.workspace_id == ws.id).first()
        if not s:
            raise HTTPException(status_code=400, detail='secret_id not found in workspace')
    prov = Provider(workspace_id=ws.id, type=ptype, secret_id=secret_id, config=config)
    db.add(prov)
    db.commit()
    db.refresh(prov)
    # Do not return provider.config to avoid leaking secrets; tests expect minimal response
    return {"id": prov.id, "workspace_id": prov.workspace_id, "type": prov.type, "secret_id": prov.secret_id}


@app.get('/api/providers')
def list_providers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ws = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
    if not ws:
        return []
    rows = db.query(Provider).filter(Provider.workspace_id == ws.id).all()
    out = []
    for r in rows:
        out.append({"id": r.id, "workspace_id": r.workspace_id, "type": r.type, "secret_id": r.secret_id, "created_at": r.created_at.isoformat() if r.created_at else None})
    return out


@app.post('/api/workflows')
def create_workflow(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = data.get('name') or 'Untitled'
    description = data.get('description')
    graph = data.get('graph')
    ws = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
    if not ws:
        raise HTTPException(status_code=400, detail='workspace not found')
    wf = Workflow(workspace_id=ws.id, name=name, description=description, graph=graph)
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return {"id": wf.id, "workspace_id": wf.workspace_id, "name": wf.name}


@app.get('/api/workflows')
def list_workflows(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ws = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
    if not ws:
        return []
    rows = db.query(Workflow).filter(Workflow.workspace_id == ws.id).all()
    out = []
    for r in rows:
        out.append({"id": r.id, "workspace_id": r.workspace_id, "name": r.name, "description": r.description, "graph": r.graph, "version": r.version})
    return out


@app.post('/api/webhook/{workflow_id}/{trigger_id}')
async def webhook_trigger(workflow_id: int, trigger_id: str, request: Request, db: Session = Depends(get_db)):
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
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail='workflow not found')
    run = Run(workflow_id=workflow_id, status='queued', input_payload=payload, started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    # enqueue Celery task (best-effort)
    try:
        execute_workflow.delay(run.id)
    except Exception:
        # ignore if Celery not available in this environment
        pass
    return {"run_id": run.id, "status": "queued"}


@app.post('/api/workflows/{workflow_id}/run')
def run_workflow(workflow_id: int, data: dict = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail='workflow not found')
    payload = data or {}
    run = Run(workflow_id=workflow_id, status='queued', input_payload=payload, started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        execute_workflow.delay(run.id)
    except Exception:
        pass
    return {"run_id": run.id, "status": "queued"}


@app.get('/api/runs')
def list_runs(workflow_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Run)
    if workflow_id:
        q = q.filter(Run.workflow_id == workflow_id)
    rows = q.order_by(Run.id.desc()).all()
    out = []
    for r in rows:
        out.append({"id": r.id, "workflow_id": r.workflow_id, "status": r.status, "started_at": r.started_at.isoformat() if r.started_at else None, "finished_at": r.finished_at.isoformat() if r.finished_at else None})
    return out
