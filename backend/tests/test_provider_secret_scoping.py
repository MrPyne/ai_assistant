import pytest


def test_provider_secret_scoping(client):
    # register first user and create a secret
    r = client.post('/api/auth/register', json={'email': 'u1@example.com', 'password': 'pass1'})
    assert r.status_code == 200
    tok1 = r.json().get('access_token')
    assert tok1

    headers1 = {'Authorization': f'Bearer {tok1}'}
    s = {'name': 'openai-key', 'value': 'sk-test-12345'}
    r2 = client.post('/api/secrets', json=s, headers=headers1)
    assert r2.status_code == 200
    secret_id = r2.json().get('id')
    assert secret_id

    # register second user
    r3 = client.post('/api/auth/register', json={'email': 'u2@example.com', 'password': 'pass2'})
    assert r3.status_code == 200
    tok2 = r3.json().get('access_token')
    assert tok2
    headers2 = {'Authorization': f'Bearer {tok2}'}

    # attempt to create provider in user2 workspace referencing user1's secret -> should fail
    p = {'type': 'openai', 'config': {}, 'secret_id': secret_id}
    r4 = client.post('/api/providers', json=p, headers=headers2)
    assert r4.status_code == 400

    # create provider in user1 workspace referencing their secret -> success
    r5 = client.post('/api/providers', json={'type': 'openai', 'secret_id': secret_id}, headers=headers1)
    assert r5.status_code in (200, 201)
    pdata = r5.json()
    # Ensure no raw config or api_key is exposed in response
    assert 'config' not in pdata or pdata.get('config') in (None, {}, [])
