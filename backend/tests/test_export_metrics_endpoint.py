import pytest
import json
import os

from backend.utils import reset_redaction_metrics, redact_secrets


def _skip_if_dummy(client):
    if hasattr(client, '_users'):
        pytest.skip('Skipping metrics export API tests in DummyClient fallback')


def test_export_metrics_success(client, tmp_path, monkeypatch):
    _skip_if_dummy(client)

    # enable persistence and point to a tmp file
    dump_file = tmp_path / "redaction_metrics_dump.ndjson"
    monkeypatch.setenv('ENABLE_METRICS_PERSISTENCE', '1')
    monkeypatch.setenv('REDACTION_METRICS_DUMP_PATH', str(dump_file))

    # create an admin user and obtain token
    resp = client.post('/api/auth/register', json={'email': 'admin@example.com', 'password': 'pass', 'role': 'admin'})
    assert resp.status_code == 200
    token = resp.json().get('access_token')
    assert token

    # produce some metrics
    reset_redaction_metrics()
    redact_secrets('sk-export-test')

    # call export endpoint
    headers = {'Authorization': f'Bearer {token}'}
    resp = client.post('/internal/redaction_metrics/export', headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get('status') == 'ok'
    assert body.get('path') == str(dump_file)

    # file should contain one newline-delimited JSON object
    assert dump_file.exists()
    data = dump_file.read_text(encoding='utf-8').strip()
    assert data
    # allow multiple lines if other tests wrote; ensure last line parses
    last_line = data.splitlines()[-1]
    payload = json.loads(last_line)
    assert 'timestamp' in payload
    assert 'metrics' in payload
    assert isinstance(payload['metrics'], dict)
    assert payload['metrics'].get('count', 0) >= 1


def test_export_metrics_disabled(client, monkeypatch):
    _skip_if_dummy(client)

    # ensure persistence disabled
    monkeypatch.delenv('ENABLE_METRICS_PERSISTENCE', raising=False)
    monkeypatch.setenv('REDACTION_METRICS_DUMP_PATH', '/tmp/should_not_be_used')

    resp = client.post('/api/auth/register', json={'email': 'admin2@example.com', 'password': 'pass', 'role': 'admin'})
    assert resp.status_code == 200
    token = resp.json().get('access_token')
    assert token

    headers = {'Authorization': f'Bearer {token}'}
    resp = client.post('/internal/redaction_metrics/export', headers=headers)
    assert resp.status_code == 400
    j = resp.json()
    assert 'error' in j
    assert 'disabled' in j['error']


def test_export_metrics_rbac_non_admin(client, monkeypatch):
    _skip_if_dummy(client)

    # enable persistence so we get past the feature flag
    monkeypatch.setenv('ENABLE_METRICS_PERSISTENCE', '1')
    monkeypatch.setenv('REDACTION_METRICS_DUMP_PATH', '/tmp/should_not_be_written')

    # create non-admin user
    resp = client.post('/api/auth/register', json={'email': 'user@example.com', 'password': 'pass'})
    assert resp.status_code == 200
    token = resp.json().get('access_token')
    assert token

    headers = {'Authorization': f'Bearer {token}'}
    resp = client.post('/internal/redaction_metrics/export', headers=headers)
    assert resp.status_code == 403
    j = resp.json()
    assert 'detail' in j or 'error' in j

