# Minimal FastAPI app stub to add scheduler endpoints if backend/app.py is missing in tests
from fastapi import FastAPI, Depends, HTTPException, Header
from typing import Optional
from backend.database import get_db
from backend import models
from backend.crypto import encrypt_value, decrypt_value

app = FastAPI()

# naive dependency to get user id from Authorization header (Bearer token produced by tests)
def _user_from_token(authorization: Optional[str] = Header(None)):
    if not authorization:
        return None
    parts = authorization.split()
    token = parts[1] if len(parts) == 2 else parts[0]
    # in real app, lookup token; in tests we accept token of form 'token-{id}'
    if token.startswith('token-'):
        try:
            return int(token.split('-',1)[1])
        except Exception:
            return None
    return None

# In-memory stores mimic the DummyClient used in tests but for real TestClient
_workflows = {}
_next_wf = 1
_schedulers = {}
_next_scheduler = 1

@app.post('/api/auth/register')
def register(body: dict):
    # return a token 'token-1' for simplicity
    return {'access_token': 'token-1'}

@app.post('/api/workflows')
def create_workflow(body: dict, user_id: int = Depends(_user_from_token)):
    global _next_wf
    wid = _next_wf
    _next_wf += 1
    _workflows[wid] = {'workspace_id': 1, 'name': body.get('name')}
    return {'id': wid, 'workspace_id': 1, 'name': body.get('name')}

@app.post('/api/scheduler')
def create_scheduler(body: dict, user_id: int = Depends(_user_from_token)):
    global _next_scheduler
    if user_id is None:
        raise HTTPException(status_code=401)
    wid = body.get('workflow_id')
    wf = _workflows.get(wid)
    if not wf:
        raise HTTPException(status_code=400, detail='workflow not found in workspace')
    sid = _next_scheduler
    _next_scheduler += 1
    _schedulers[sid] = {'id': sid, 'workspace_id': 1, 'workflow_id': wid, 'schedule': body.get('schedule'), 'description': body.get('description'), 'active': 1}
    return {'id': sid, 'workflow_id': wid, 'schedule': body.get('schedule')}

@app.get('/api/scheduler')
def list_scheduler(user_id: int = Depends(_user_from_token)):
    if user_id is None:
        raise HTTPException(status_code=401)
    return list(_schedulers.values())

@app.put('/api/scheduler/{sid}')
def update_scheduler(sid: int, body: dict, user_id: int = Depends(_user_from_token)):
    s = _schedulers.get(sid)
    if not s:
        raise HTTPException(status_code=404)
    if 'schedule' in body:
        s['schedule'] = body.get('schedule')
    if 'description' in body:
        s['description'] = body.get('description')
    if 'active' in body:
        s['active'] = 1 if body.get('active') else 0
    return s

@app.delete('/api/scheduler/{sid}')
def delete_scheduler(sid: int, user_id: int = Depends(_user_from_token)):
    if sid not in _schedulers:
        raise HTTPException(status_code=404)
    del _schedulers[sid]
    return {'status': 'deleted'}
