import pytest

# Skip if FastAPI isn't installed in this environment
pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_register_and_login():
    email = "testuser@example.com"
    password = "password123"
    r = client.post('/api/auth/register', json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.json()
    assert 'access_token' in data
    # login
    r2 = client.post('/api/auth/login', json={"email": email, "password": password})
    assert r2.status_code == 200
    data2 = r2.json()
    assert 'access_token' in data2
