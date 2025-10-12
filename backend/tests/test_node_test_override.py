import pytest

# Skip this test module when SQLAlchemy is not available in the environment.
pytest.importorskip('sqlalchemy')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import app as appmod
from backend.database import Base
from backend.models import User, Workspace, Secret, Provider
from backend.crypto import encrypt_value


def test_node_test_respects_override_secret_id(monkeypatch):
    """Ensure node_test applies _override_secret_id in-memory for the test
    call (adapter sees overridden secret_id) and does not persist the change
    to the DB (provider.secret_id remains unchanged after the call).
    """
    # Setup an in-memory DB and bind app.SessionLocal to it
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # create tables
    Base.metadata.create_all(bind=engine)

    # point app to testing session
    appmod.SessionLocal = TestingSessionLocal
    appmod._DB_AVAILABLE = True

    db = TestingSessionLocal()
    try:
        # create user and workspace
        user = User(email='override@example.com', hashed_password='x')
        db.add(user)
        db.commit()
        db.refresh(user)
        ws = Workspace(name='override-ws', owner_id=user.id)
        db.add(ws)
        db.commit()
        db.refresh(ws)

        # create two secrets: original and override
        secret_orig_value = 'sk-orig-AAA'
        secret_override_value = 'sk-override-BBB'
        s1 = Secret(workspace_id=ws.id, name='orig', encrypted_value=encrypt_value(secret_orig_value), created_by=user.id)
        db.add(s1)
        db.commit()
        db.refresh(s1)

        s2 = Secret(workspace_id=ws.id, name='override', encrypted_value=encrypt_value(secret_override_value), created_by=user.id)
        db.add(s2)
        db.commit()
        db.refresh(s2)

        # create provider referencing the original secret
        p = Provider(workspace_id=ws.id, secret_id=s1.id, type='openai', config={})
        db.add(p)
        db.commit()
        db.refresh(p)

        # Capture which secret_id the adapter sees by monkeypatching the
        # OpenAIAdapter used by node_test. We record observed secret_ids in
        # the `seen` list for assertion.
        seen = []

        class CapturingAdapter:
            def __init__(self, provider, db=None):
                # record what provider.secret_id is at construction time
                try:
                    seen.append(getattr(provider, 'secret_id', None))
                except Exception:
                    seen.append(None)

            def generate(self, prompt, **kws):
                return {"text": "ok"}

        # Patch the real adapter in the adapters module so the dynamic import
        # inside node_test picks up our CapturingAdapter.
        import backend.adapters.openai_adapter as oai_mod

        monkeypatch.setattr(oai_mod, 'OpenAIAdapter', CapturingAdapter)

        # Call the node_test handler directly via the app compatibility mapping
        client = appmod.app._routes.get(('POST', '/api/node_test'))
        assert client is not None

        body = {
            'node': {
                'type': 'llm',
                'prompt': 'Hello override',
                'provider_id': p.id,
                '_override_secret_id': s2.id,
            }
        }

        res = client(body)
        # ensure adapter was invoked and captured the override
        assert seen, 'adapter was not constructed'
        assert seen[0] == s2.id

        # re-load provider from DB to ensure secret_id persisted unchanged
        prov_after = db.query(Provider).filter(Provider.id == p.id).first()
        assert prov_after.secret_id == s1.id

    finally:
        db.close()
