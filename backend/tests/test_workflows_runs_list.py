import pytest
from fastapi.testclient import TestClient
from backend.app import app


def test_list_runs_for_workflow(client: TestClient):
    # Register a user and create a workflow
    r = client.post('/api/auth/register', json={'email': 'a@example.com', 'password': 'pass'})
    assert r.status_code == 200
    token = r.json()['access_token']

    # Create a workflow
    r2 = client.post('/api/workflows', json={'name': 'W1'}, headers={'Authorization': token})
    assert r2.status_code == 201
    wf_id = r2.json()['id']

    # Trigger a run via the manual run endpoint
    r3 = client.post(f'/api/workflows/{wf_id}/run', json={}, headers={'Authorization': token})
    assert r3.status_code == 200
    run_id = r3.json()['run_id']

    # Now list runs for the workflow
    r4 = client.get(f'/api/workflows/{wf_id}/runs', headers={'Authorization': token})
    assert r4.status_code == 200
    runs = r4.json()
    assert isinstance(runs, list)
    assert any(r.get('id') == run_id for r in runs)
