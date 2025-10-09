import pytest
from fastapi.testclient import TestClient

# Reuse the real TestClient provided by conftest.py

def test_create_workflow_accepts_empty_graph(client: TestClient):
    wf = {"name": "empty-graph", "graph": None}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code in (200, 201)


def test_create_workflow_rejects_invalid_shape(client: TestClient):
    # graph must be dict with nodes or list
    wf = {"name": "bad-graph", "graph": 123}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code == 400
    assert 'graph must be' in r.json().get('detail')


def test_create_workflow_rejects_http_missing_url(client: TestClient):
    # react-flow style node without url
    wf = {
        "name": "bad-http",
        "graph": {"nodes": [{"id": "n1", "data": {"label": "HTTP Request", "config": {}}}]}
    }
    r = client.post('/api/workflows', json=wf)
    assert r.status_code == 400
    detail = r.json().get('detail')
    # support structured error detail ({message, node_id}) or plain string
    if isinstance(detail, dict):
        msg = detail.get('message') or detail.get('detail') or ''
    else:
        msg = detail or ''
    assert 'http node' in msg


def test_create_workflow_rejects_llm_missing_prompt(client: TestClient):
    wf = {
        "name": "bad-llm",
        "graph": {"nodes": [{"id": "n1", "data": {"label": "LLM", "config": {}}}]}
    }
    r = client.post('/api/workflows', json=wf)
    assert r.status_code == 400
    detail = r.json().get('detail')
    if isinstance(detail, dict):
        msg = detail.get('message') or detail.get('detail') or ''
    else:
        msg = detail or ''
    assert 'llm node' in msg


def test_create_workflow_rejects_node_missing_id(client: TestClient):
    wf = {"name": "no-id", "graph": {"nodes": [{"data": {"label": "LLM", "config": {"prompt": "hi"}}}]}}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code == 400
    detail = r.json().get('detail')
    if isinstance(detail, dict):
        msg = detail.get('message') or detail.get('detail') or ''
    else:
        msg = detail or ''
    assert 'missing id' in msg


def test_update_workflow_accepts_empty_graph(client: TestClient):
    # create workflow first
    wf = {"name": "to-update", "graph": None}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code in (200, 201)
    wid = r.json().get('id')
    # update with empty graph
    up = {"name": "updated", "graph": None}
    r2 = client.put(f'/api/workflows/{wid}', json=up)
    assert r2.status_code in (200, 201)


def test_update_workflow_rejects_http_missing_url(client: TestClient):
    # create valid workflow
    wf = {"name": "upd-bad-http", "graph": {"nodes": [{"id": "n1", "data": {"label": "HTTP Request", "config": {"url": "http://ok"}}}]}}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code in (200, 201)
    wid = r.json().get('id')
    # attempt update that removes url
    bad = {"graph": {"nodes": [{"id": "n1", "data": {"label": "HTTP Request", "config": {}}}]}}
    r2 = client.put(f'/api/workflows/{wid}', json=bad)
    assert r2.status_code == 400
    detail = r2.json().get('detail')
    if isinstance(detail, dict):
        msg = detail.get('message') or detail.get('detail') or ''
    else:
        msg = detail or ''
    assert 'http node' in msg


def test_update_workflow_rejects_llm_missing_prompt(client: TestClient):
    wf = {"name": "upd-bad-llm", "graph": {"nodes": [{"id": "n1", "data": {"label": "LLM", "config": {"prompt": "ok"}}}]}}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code in (200, 201)
    wid = r.json().get('id')
    bad = {"graph": {"nodes": [{"id": "n1", "data": {"label": "LLM", "config": {}}}]}}
    r2 = client.put(f'/api/workflows/{wid}', json=bad)
    assert r2.status_code == 400
    detail = r2.json().get('detail')
    if isinstance(detail, dict):
        msg = detail.get('message') or detail.get('detail') or ''
    else:
        msg = detail or ''
    assert 'llm node' in msg


def test_update_workflow_rejects_node_missing_id(client: TestClient):
    wf = {"name": "upd-no-id", "graph": {"nodes": [{"id": "n1", "data": {"label": "LLM", "config": {"prompt": "hi"}}}]}}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code in (200, 201)
    wid = r.json().get('id')
    bad = {"graph": {"nodes": [{"data": {"label": "LLM", "config": {"prompt": "hi"}}}]}}
    r2 = client.put(f'/api/workflows/{wid}', json=bad)
    assert r2.status_code == 400
    detail = r2.json().get('detail')
    if isinstance(detail, dict):
        msg = detail.get('message') or detail.get('detail') or ''
    else:
        msg = detail or ''
    assert 'missing id' in msg
