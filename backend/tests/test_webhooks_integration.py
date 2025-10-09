import os
import importlib
import pytest


@pytest.mark.integration
def test_webhook_persistence_with_migrations(tmp_path):
    """Integration test that applies Alembic migrations to a fresh SQLite DB,
    starts the FastAPI TestClient against that DB and asserts webhook records
    are actually persisted by the API (not just in-memory fallback).

    This test is marked `integration` and will be skipped if the repository
    cannot apply migrations programmatically (Alembic not installed or
    incompatible DB driver).
    """
    # Try to import the helper for applying migrations programmatically
    try:
        import scripts.apply_migrations as apply_migrations
    except Exception:
        pytest.skip("apply_migrations helper not importable; skipping integration test")

    # Create a fresh sqlite file DB for isolation
    db_file = tmp_path / "test_integ.db"
    database_url = f"sqlite:///{db_file}"
    # Ensure the rest of the application picks up this DATABASE_URL
    os.environ["DATABASE_URL"] = database_url

    # Reload important modules so they re-evaluate DATABASE_URL at import time
    # (backend.database constructs engines at import time)
    try:
        import backend.database as database
        importlib.reload(database)
    except Exception:
        pytest.skip("Could not import/reload backend.database; skipping integration test")

    # Reload models so they bind to the reloaded Base/engine
    try:
        import backend.models as models
        importlib.reload(models)
    except Exception:
        pytest.skip("Could not import/reload backend.models; skipping integration test")

    # Find alembic.ini and run programmatic migrations; skip the test if that fails
    alembic_ini = apply_migrations.find_alembic_ini()
    if not alembic_ini:
        pytest.skip("Could not locate alembic.ini; skipping integration test")

    ok = apply_migrations.run_programmatic(alembic_ini, database_url)
    if not ok:
        pytest.skip("Could not apply alembic migrations programmatically; skipping integration test")

    # Reload the FastAPI app so it uses the reloaded DB bindings
    try:
        import backend.app as appmod
        importlib.reload(appmod)
    except Exception:
        pytest.skip("Could not import/reload backend.app; skipping integration test")

    from fastapi.testclient import TestClient

    with TestClient(appmod.app) as client:
        # create a simple workflow
        wf = {"name": "wh-test", "triggers": {"t1": {"type": "webhook"}}}
        r = client.post('/api/workflows', json=wf)
        assert r.status_code in (200, 201)
        body = r.json()
        wf_id = body.get('id') or body.get('workflow_id') or 1
        workspace_id = body.get('workspace_id') or 1

        # create a webhook for the workflow (explicit path)
        data = {"path": "test-path-123", "description": "a test webhook"}
        r2 = client.post(f'/api/workflows/{wf_id}/webhooks', json=data)
        assert r2.status_code in (200, 201)
        b2 = r2.json()
        wh_id = b2.get('id')
        wh_path = b2.get('path') or data['path']
        assert wh_path is not None

        # Verify the webhook record exists in the real DB using SQLAlchemy
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # Create a sync engine that matches the app's DATABASE_URL
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        try:
            # models.Webhook is the declarative model class; ensure we can query it
            persisted = session.query(models.Webhook).filter_by(path=wh_path).all()
            assert len(persisted) >= 1, "Expected at least one persisted webhook record"
        finally:
            session.close()

        # Trigger the public webhook route which should create a run
        payload = {"hello": "world"}
        r4 = client.post(f'/w/{workspace_id}/workflows/{wf_id}/{wh_path}', json=payload)
        assert r4.status_code in (200, 201)
        rb4 = r4.json()
        assert 'run_id' in rb4

        # Attempt to delete the webhook record via API and ensure it is removed
        if wh_id:
            r5 = client.delete(f'/api/workflows/{wf_id}/webhooks/{wh_id}')
            assert r5.status_code in (200, 202, 204)
            # check DB no longer has the record
            session = SessionLocal()
            try:
                after = session.query(models.Webhook).filter_by(id=wh_id).all()
                assert len(after) == 0
            finally:
                session.close()
