import pytest
pytest.importorskip('sqlalchemy')
from backend.database import SessionLocal
from backend.models import User, Workspace, Workflow, Run, RunLog
from backend.crypto import encrypt_value
from backend import tasks
import requests


def test_http_node_redacts_authorization_header(monkeypatch):
    # Setup in-memory DB objects
    db = SessionLocal()
    try:
        # create user and workspace
        user = User(email='u@example.com', hashed_password='x')
        db.add(user)
        db.commit()
        db.refresh(user)
        ws = Workspace(name='w', owner_id=user.id)
        db.add(ws)
        db.commit()
        db.refresh(ws)

        # create workflow with an HTTP node that includes an Authorization header
        graph = {
            'nodes': [
                {
                    'id': 'n1',
                    'type': 'http',
                    'method': 'POST',
                    'url': 'http://example.invalid/test',
                    'headers': {'Authorization': 'Bearer secret-token-ABC123'},
                    'body': {'foo': 'bar'},
                }
            ]
        }
        wf = Workflow(workspace_id=ws.id, name='wf', graph=graph)
        db.add(wf)
        db.commit()
        db.refresh(wf)

        # create run
        run = Run(workflow_id=wf.id, status='queued', input_payload={})
        db.add(run)
        db.commit()
        db.refresh(run)

        # monkeypatch requests.post to raise an exception that includes the token
        def fake_post(url, headers=None, json=None, timeout=None):
            raise Exception(f"Request failed. Authorization: {headers.get('Authorization')}")

        monkeypatch.setattr(requests, 'post', fake_post)

        # process the run
        res = tasks.process_run(run.id)

        # fetch logs for the run and ensure the secret token is not present
        logs = db.query(RunLog).filter(RunLog.run_id == run.id).all()
        combined = "\n".join([l.message or "" for l in logs])
        assert 'secret-token-ABC123' not in combined
        # assert redaction placeholder present
        assert '[REDACTED]' in combined

    finally:
        db.close()
