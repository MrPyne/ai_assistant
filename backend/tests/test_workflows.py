import pytest


def test_webhook_creates_run(client):
    # Minimal test to ensure webhook trigger creates a run and logs are accessible.
    wf = {"name": "test", "triggers": {"trigger1": {"type": "webhook"}}}
    r1 = client.post('/api/workflows', json=wf)
    assert r1.status_code in (200, 201)
    wf_id = r1.json().get("id") or r1.json().get("workflow_id") or "1"

    r3 = client.post(f'/api/webhook/{wf_id}/trigger1', json={"hello": "world"})
    assert r3.status_code == 200
    assert 'run_id' in r3.json()
    run_id = r3.json()['run_id']

    # fetch logs (should be empty or present)
    r4 = client.get(f'/api/runs/{run_id}/logs')
    assert r4.status_code == 200
    # verify logs response shape matches the LogsResponse schema
    body = r4.json()
    assert isinstance(body, dict)
    assert 'logs' in body and isinstance(body['logs'], list)
