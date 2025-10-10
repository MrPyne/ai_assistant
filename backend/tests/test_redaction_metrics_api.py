import pytest
from backend.utils import redact_secrets, get_redaction_metrics


def test_reset_endpoint_resets_metrics(client):
    # Skip when using the DummyClient fallback (conftest provides a DummyClient
    # in lightweight environments where FastAPI isn't installed). The DummyClient
    # does not exercise our FastAPI route, so this test only runs when the
    # real TestClient + app are available.
    if hasattr(client, '_users'):
        pytest.skip('Skipping API reset test in DummyClient fallback')

    # create an admin user and obtain token
    resp = client.post('/api/auth/register', json={'email': 'admin@example.com', 'password': 'pass', 'role': 'admin'})
    assert resp.status_code == 200
    token = resp.json().get('access_token')
    assert token

    # create a redaction event
    redact_secrets('sk-abcdefghijklmnop')
    metrics = get_redaction_metrics()
    assert metrics['count'] >= 1

    # call protected reset endpoint
    headers = {'Authorization': f'Bearer {token}'}
    resp2 = client.post('/internal/redaction_metrics/reset', headers=headers)
    assert resp2.status_code == 200

    metrics2 = get_redaction_metrics()
    assert metrics2['count'] == 0
