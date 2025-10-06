import pytest


def test_runs_access_control(client):
    # The dummy test client used in some dev environments does not enforce
    # workspace scoping for endpoints. Skip this test when running against the
    # dummy client so local lightweight test runs don't fail.
    if hasattr(client, "_users"):
        pytest.skip("Dummy client doesn't enforce access control; run full tests with FastAPI TestClient")

    # Register two users (A and B)
    r = client.post('/api/auth/register', json={'email': 'a@example.com', 'password': 'pass'})
    assert r.status_code == 200
    token_a = r.json()['access_token']

    r2 = client.post('/api/auth/register', json={'email': 'b@example.com', 'password': 'pass'})
    assert r2.status_code == 200
    token_b = r2.json()['access_token']

    # User A creates a workflow and triggers a run
    r3 = client.post('/api/workflows', json={'name': 'W1'}, headers={'Authorization': token_a})
    assert r3.status_code in (200, 201)
    wf_id = r3.json()['id']

    r4 = client.post(f'/api/workflows/{wf_id}/run', json={}, headers={'Authorization': token_a})
    assert r4.status_code in (200, 201)
    run_id = r4.json().get('run_id')
    assert run_id is not None

    # User B should NOT be able to list runs for User A's workflow.
    # The API may return 403 or 404 for unauthorized access depending on implementation.
    r5 = client.get(f'/api/workflows/{wf_id}/runs', headers={'Authorization': token_b})
    assert r5.status_code in (403, 404)
