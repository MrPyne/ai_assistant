import pytest
pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from backend.app import app


def test_debug_print():
    client = TestClient(app)
    r = client.post('/api/auth/register', json={'email':'dbg@example.com','password':'p'})
    print('STATUS', r.status_code)
    try:
        print('TEXT', r.text)
    except Exception:
        print('TEXTERR')
    try:
        print('JSON', r.json())
    except Exception as e:
        print('JSONERR', e)
    assert r.status_code == 200
