import os
import pytest
from backend.app import app


def test_node_test_llm_mock(monkeypatch):
    # No LIVE_LLM, no DB/provider -> returns mock response
    client = app._routes.get(('POST', '/api/node_test'))
    # call directly since app in tests exposes compat wrappers
    body = {'node': {'type': 'llm', 'prompt': 'Hello world'}}
    res = client(body)
    assert 'result' in res
    assert isinstance(res['result'], dict)
    assert '[mock' in res['result'].get('text', '')


def test_node_test_http_mock(monkeypatch):
    client = app._routes.get(('POST', '/api/node_test'))
    body = {'node': {'type': 'http', 'method': 'GET', 'url': 'https://example.com', 'headers': {'Authorization': 'Bearer secret-token'}}}
    res = client(body)
    assert 'result' in res
    assert isinstance(res['result'], dict)
    # LIVE_HTTP disabled by default so we get mock text
    assert res['result'].get('text') == '[mock] http blocked by LIVE_HTTP' or '[mock' in res['result'].get('text', '')


@pytest.mark.parametrize('env_val', ['true', 'false'])
def test_node_test_respects_live_http(monkeypatch, env_val):
    monkeypatch.setenv('LIVE_HTTP', env_val)
    client = app._routes.get(('POST', '/api/node_test'))
    body = {'node': {'type': 'http', 'method': 'GET', 'url': 'https://example.com'}}
    res = client(body)
    assert 'result' in res


def test_node_test_invalid_node():
    client = app._routes.get(('POST', '/api/node_test'))
    res = client({'node': None})
    assert 'error' in res
