import pytest
from fastapi.testclient import TestClient

# Tests to assert the backend returns structured validation errors with node_id
# when it can be inferred. These are low-risk unit tests that codify the
# contract used by the editor to focus offending nodes.


def test_create_workflow_returns_node_id_in_validation_error(client: TestClient):
    wf = {
        "name": "bad-http-node-id",
        "graph": {"nodes": [{"id": "n1", "data": {"label": "HTTP Request", "config": {}}}]}
    }
    r = client.post('/api/workflows', json=wf)
    assert r.status_code == 400
    body = r.json()
    # Spec: response should include a top-level message and (when available) node_id
    assert 'message' in body
    assert body.get('message') is not None
    assert 'node_id' in body
    assert str(body.get('node_id')) == 'n1'


def test_create_workflow_invalid_shape_returns_node_id_from_index(client: TestClient):
    # An element that is a dict but lacks 'data' and 'type' is considered an
    # invalid shape; the validator should still try to resolve the node id by
    # index and include it in the structured error detail.
    wf = {"name": "bad-shape-node-id", "graph": {"nodes": [{"id": "bad1"}]}}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code == 400
    body = r.json()
    assert 'message' in body
    assert 'node_id' in body
    assert str(body.get('node_id')) == 'bad1'


def test_update_workflow_returns_node_id_in_validation_error(client: TestClient):
    # Create a valid workflow first, then attempt an update that makes the
    # http node invalid (missing url). The update validator should return a
    # structured error with the offending node_id.
    wf = {"name": "to-update-nodeid", "graph": {"nodes": [{"id": "n2", "data": {"label": "HTTP Request", "config": {"url": "http://ok"}}}]}}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code in (200, 201)
    wid = r.json().get('id')
    bad = {"graph": {"nodes": [{"id": "n2", "data": {"label": "HTTP Request", "config": {}}}]}}
    r2 = client.put(f'/api/workflows/{wid}', json=bad)
    assert r2.status_code == 400
    body = r2.json()
    assert 'message' in body
    assert 'node_id' in body
    assert str(body.get('node_id')) == 'n2'
