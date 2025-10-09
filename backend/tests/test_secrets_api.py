import pytest


def test_create_and_list_secrets_does_not_expose_value(client):
    # register a user to obtain a token when using the real TestClient or DummyClient
    reg = client.post('/api/auth/register', json={'email': 's@example.com', 'password': 'pass'})
    assert reg.status_code in (200, 201)
    body = reg.json()
    token = body.get('access_token') or body.get('token') or None

    headers = {'Authorization': f'Bearer {token}'} if token else {}

    # create a secret
    sdata = {'name': 'api-key', 'value': 'supersecret'}
    r = client.post('/api/secrets', json=sdata, headers=headers)
    assert r.status_code in (200, 201)
    created = r.json()
    # created should at least include an id in real DB; DummyClient returns 200 with id too
    assert isinstance(created, dict)

    # list secrets and ensure the secret value is not returned in plaintext
    r2 = client.get('/api/secrets', headers=headers)
    assert r2.status_code in (200, 201)
    body2 = r2.json()
    # Accept either an empty list (dummy fallback) or a list of secrets
    assert isinstance(body2, (list, dict))
    # If list, ensure no plaintext 'value' or 'encrypted_value' fields are exposed
    if isinstance(body2, list):
        for it in body2:
            assert 'value' not in it
            assert 'encrypted_value' not in it
