import pytest


def test_http_exception_non_dict_detail_normalized(client):
    """Ensure real FastAPI + TestClient receive our normalized 400 envelope.

    This test is intended to run in environments with FastAPI installed where
    conftest provides a real TestClient. If the lightweight DummyClient is in
    use (fastapi not present), skip the test — the DummyClient already
    implements the expected behavior for unit tests.
    """
    # Skip when running with the DummyClient fallback used in lightweight
    # environments (it does not expose the TestClient 'app' attribute).
    if not hasattr(client, 'app'):
        pytest.skip('requires FastAPI TestClient')

    # Calling resend without an email triggers HTTPException(status_code=400,
    # detail='email required') inside the app. Our custom exception handler
    # should normalize this to a top-level {'message': 'email required'}.
    r = client.post('/api/auth/resend', json={})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body, dict)
    # Spec: top-level human-friendly message
    assert 'message' in body
    assert body.get('message') == 'email required'
    # Handler should not nest this under 'detail'
    assert 'detail' not in body


def test_http_exception_dict_detail_pass_through(client):
    """If the app raises an HTTPException with a dict detail (message/node_id),
    FastAPI + our handler should preserve the structured dict shape and return
    the same top-level keys to the client. Skip when DummyClient is in use.
    """
    if not hasattr(client, 'app'):
        pytest.skip('requires FastAPI TestClient')

    # Use the create_workflow endpoint which performs validation and raises a
    # structured dict detail like {'message': ..., 'node_id': ...} for invalid
    # graphs. Provide a graph that triggers a missing-url http node error.
    wf = {"name": "bad-http-node", "graph": {"nodes": [{"id": "nid", "data": {"label": "HTTP Request", "config": {}}}]}}
    r = client.post('/api/workflows', json=wf)
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body, dict)
    # Should include human-friendly message and node_id preserved
    assert 'message' in body
    assert 'node_id' in body
    assert str(body.get('node_id')) == 'nid'
