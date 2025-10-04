import os
import pytest

# Skip this test module when SQLAlchemy is not installed in the environment.
pytest.importorskip('sqlalchemy')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend import tasks
from backend.database import Base
from backend.models import User, Workspace, Secret, Provider, Workflow, Run, RunLog
from backend.crypto import encrypt_value


def test_adapter_does_not_persist_api_key():
    # Setup in-memory DB and bind tasks.SessionLocal to it
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # create tables
    Base.metadata.create_all(bind=engine)

    # monkeypatch tasks to use our testing session
    tasks.SessionLocal = TestingSessionLocal

    db = TestingSessionLocal()
    try:
        # create user and workspace
        user = User(email='leaktest@example.com', hashed_password='x')
        db.add(user)
        db.commit()
        db.refresh(user)
        ws = Workspace(name='leak-ws', owner_id=user.id)
        db.add(ws)
        db.commit()
        db.refresh(ws)

        # create secret with a value that would be obviously sensitive
        secret_value = 'sk-test-LEAK-12345'
        encrypted = encrypt_value(secret_value)
        s = Secret(workspace_id=ws.id, name='openai-key', encrypted_value=encrypted, created_by=user.id)
        db.add(s)
        db.commit()
        db.refresh(s)

        # create provider referencing the secret
        p = Provider(workspace_id=ws.id, secret_id=s.id, type='openai', config={})
        db.add(p)
        db.commit()
        db.refresh(p)

        # create workflow with a single llm node referencing provider
        graph = {'nodes': [{'id': 'n1', 'type': 'llm', 'provider_id': p.id, 'prompt': 'Hello secret testing'}]}
        wf = Workflow(workspace_id=ws.id, name='wf1', description='test', graph=graph)
        db.add(wf)
        db.commit()
        db.refresh(wf)

        # create run
        run = Run(workflow_id=wf.id, status='queued', input_payload={})
        db.add(run)
        db.commit()
        db.refresh(run)

        # ensure LIVE_LLM is disabled so adapter uses mock path but still may decrypt the key
        os.environ.pop('LIVE_LLM', None)
        os.environ.pop('ENABLE_OPENAI', None)

        # process the run (this will call adapters and write RunLogs)
        res = tasks.process_run(run.id)

        # reload logs from DB and ensure secret_value is not present anywhere
        logs = db.query(RunLog).filter(RunLog.run_id == run.id).all()
        combined = '\n'.join([l.message or '' for l in logs])
        assert secret_value not in combined

        # ensure output payload (if any) does not include secret
        r = db.query(Run).filter(Run.id == run.id).first()
        outpayload = r.output_payload or {}
        assert secret_value not in str(outpayload)

    finally:
        db.close()
