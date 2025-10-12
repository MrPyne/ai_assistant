import pytest

# Skip this test module when SQLAlchemy is not available in the environment.
pytest.importorskip('sqlalchemy')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import app as appmod
from backend.database import Base
from backend.models import User, Workspace, Secret, Provider
from backend.crypto import encrypt_value


def test_node_test_passes_decrypted_secret_to_adapter(monkeypatch):
    """Ensure node_test resolves and passes the decrypted secret value to
    the adapter when an override secret id is provided. Also verify the
    override is transient and not persisted to the Provider row.
    """
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
        user = User(email='dec@example.com', hashed_password='x')
        db.add(user)
        db.commit()
        db.refresh(user)
        ws = Workspace(name='dec-ws', owner_id=user.id)
        db.add(ws)
        db.commit()
        db.refresh(ws)

        # create two secrets: original and override
        secret_orig_value = 'sk-orig-CCC'
        secret_override_value = 'sk-override-DDD'
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

        # Capture what the adapter sees: both the provider.secret_id and the
        # decrypted api key value resolved from the DB.
        seen = {}

        class CapturingAdapter:
            def __init__(self, provider, db=None):
                # record what provider.secret_id is at construction time
                try:
                    seen['secret_id'] = getattr(provider, 'secret_id', None)
                except Exception:
                    seen['secret_id'] = None

                # attempt to resolve decrypted key like the real adapter does
                try:
                    if db is not None:
                        from backend.models import Secret as _Secret
                        row = db.query(_Secret).filter(_Secret.id == getattr(provider, 'secret_id', None), _Secret.workspace_id == getattr(provider, 'workspace_id', None)).first()
                        if row:
                            # decrypt_value imported lazily to mirror adapter behaviour
                            seen['api_key'] = __import__('backend.crypto', fromlist=['decrypt_value']).decrypt_value(row.encrypted_value)
                        else:
                            seen['api_key'] = None
                    else:
                        seen['api_key'] = None
                except Exception:
                    seen['api_key'] = None

            def generate(self, prompt, **kws):
                return {"text": "ok"}

        # Patch the real adapter in the adapters module so node_test picks up
        # our CapturingAdapter when it dynamically imports the adapter.
        import backend.adapters.openai_adapter as oai_mod

        monkeypatch.setattr(oai_mod, 'OpenAIAdapter', CapturingAdapter)

        # Call the node_test handler directly via the app compatibility mapping
        client = appmod.app._routes.get(('POST', '/api/node_test'))
        assert client is not None

        body = {
            'node': {
                'type': 'llm',
                'prompt': 'Hello decrypt',
                'provider_id': p.id,
                '_override_secret_id': s2.id,
            }
        }

        res = client(body)

        # ensure adapter was invoked and captured both values
        assert 'secret_id' in seen and 'api_key' in seen, 'adapter did not capture expected values'
        assert seen['secret_id'] == s2.id
        assert seen['api_key'] == secret_override_value

        # verify provider row in DB still references the original secret id
        prov_after = db.query(Provider).filter(Provider.id == p.id).first()
        assert prov_after.secret_id == s1.id

    finally:
        db.close()
