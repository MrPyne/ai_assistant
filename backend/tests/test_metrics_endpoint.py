import pytest
import builtins

from backend.utils import redact_secrets, get_redaction_metrics, reset_redaction_metrics


def _skip_if_dummy(client):
    if hasattr(client, '_users'):
        pytest.skip('Skipping metrics API tests in DummyClient fallback')


def test_metrics_json_fallback(client, monkeypatch):
    _skip_if_dummy(client)

    # Ensure prometheus_client import fails inside the endpoint by
    # monkeypatching __import__ to raise ImportError for that package.
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'prometheus_client' or name.startswith('prometheus_client.'):
            raise ImportError('No module named prometheus_client')
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', fake_import)

    try:
        reset_redaction_metrics()
        redact_secrets('sk-test-json-fallback')
        resp = client.get('/metrics')
        assert resp.status_code == 200
        # When prometheus_client isn't available the endpoint should return JSON
        data = resp.json()
        assert isinstance(data, dict)
        assert 'count' in data
        assert data['count'] >= 1
    finally:
        # restore import behavior
        monkeypatch.setattr(builtins, '__import__', real_import)


def test_metrics_prometheus_format(client):
    _skip_if_dummy(client)

    reset_redaction_metrics()
    redact_secrets('sk-test-prom')
    resp = client.get('/metrics')
    assert resp.status_code == 200
    # When prometheus_client is available the endpoint should return the
    # Prometheus exposition format content type and include our metric name.
    ct = resp.headers.get('content-type', '')
    assert 'text/plain' in ct or 'application/vnd.google.protobuf' in ct or 'application/octet-stream' in ct
    # The payload should include the metric name we register
    body = resp.content
    assert b'redaction_total_count' in body
