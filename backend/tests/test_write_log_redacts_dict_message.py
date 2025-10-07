import pytest
pytest.importorskip('sqlalchemy')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend import tasks
from backend.database import Base
from backend.models import User, Workspace, Workflow, Run, RunLog


def test_write_log_redacts_dict_message():
    """Ensure _write_log redacts secret-like values when message is a dict."""
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)

    # use a real session instance for _write_log
    db = TestingSessionLocal()
    try:
        # create minimal objects needed for referential integrity
        user = User(email='u2@example.com', hashed_password='x')
        db.add(user)
        db.commit()
        db.refresh(user)
        ws = Workspace(name='w2', owner_id=user.id)
        db.add(ws)
        db.commit()
        db.refresh(ws)

        wf = Workflow(workspace_id=ws.id, name='wf', graph={})
        db.add(wf)
        db.commit()
        db.refresh(wf)

        run = Run(workflow_id=wf.id, status='queued', input_payload={})
        db.add(run)
        db.commit()
        db.refresh(run)

        # message contains an obvious API key that should be redacted
        secret_payload = {'headers': {'Authorization': 'Bearer sk-SECRET-XYZ'}, 'body': {'api_key': 'sk-ABCDEF'}}
        tasks._write_log(db, run.id, 'n1', 'info', secret_payload)

        logs = db.query(RunLog).filter(RunLog.run_id == run.id).all()
        assert logs, 'Expected at least one RunLog row'
        combined = "\n".join([l.message or "" for l in logs])
        # raw secret fragments must not be present
        assert 'sk-SECRET-XYZ' not in combined
        assert 'sk-ABCDEF' not in combined
        # redaction placeholder should be present
        assert '[REDACTED]' in combined

    finally:
        db.close()
