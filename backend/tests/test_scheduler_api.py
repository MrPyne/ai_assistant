import pytest


def test_scheduler_crud_flow(client):
    # register user and get token
    r = client.post('/api/auth/register', json={'email': 's@test', 'password': 'pass'})
    assert r.status_code == 200
    token = r.json().get('access_token')
    assert token
    headers = {'Authorization': f'Bearer {token}'}

    # create a workflow
    r = client.post('/api/workflows', json={'name': 'SchedWF'}, headers=headers)
    assert r.status_code in (200, 201)
    wid = r.json().get('id')
    assert wid

    # create scheduler entry
    r = client.post('/api/scheduler', json={'workflow_id': wid, 'schedule': '60', 'description': 'every 60s'}, headers=headers)
    assert r.status_code == 201
    sid = r.json().get('id')
    assert sid

    # list schedulers
    r = client.get('/api/scheduler', headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert any(i.get('id') == sid for i in items)

    # update scheduler
    r = client.put(f'/api/scheduler/{sid}', json={'schedule': '120', 'active': False}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data.get('schedule') == '120'
    assert data.get('active') in (0, False)

    # delete scheduler
    r = client.delete(f'/api/scheduler/{sid}', headers=headers)
    assert r.status_code == 200

    # ensure it's gone
    r = client.get('/api/scheduler', headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert not any(i.get('id') == sid for i in items)
