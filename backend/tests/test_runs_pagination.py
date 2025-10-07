import pytest


def test_runs_pagination_and_total_count(client):
    # Register and create a workflow
    r = client.post('/api/auth/register', json={'email': 'p@example.com', 'password': 'pass'})
    assert r.status_code == 200
    token = r.json()['access_token']

    r2 = client.post('/api/workflows', json={'name': 'PaginWF'}, headers={'Authorization': token})
    assert r2.status_code in (200, 201)
    wf_id = r2.json()['id']

    # create many runs (> limit)
    total_runs = 60
    for i in range(total_runs):
        r3 = client.post(f'/api/workflows/{wf_id}/run', json={}, headers={'Authorization': token})
        assert r3.status_code in (200, 201)

    # request with small limit
    r4 = client.get(f'/api/runs?workflow_id={wf_id}&limit=10&offset=0', headers={'Authorization': token})
    assert r4.status_code == 200
    page = r4.json()
    assert isinstance(page, dict)
    assert 'items' in page and isinstance(page['items'], list)
    assert 'total' in page and isinstance(page['total'], int)
    assert page['total'] >= total_runs
    assert len(page['items']) == 10

    # request next page using offset
    r5 = client.get(f'/api/runs?workflow_id={wf_id}&limit=10&offset=10', headers={'Authorization': token})
    assert r5.status_code == 200
    page2 = r5.json()
    assert isinstance(page2, dict)
    assert 'items' in page2 and isinstance(page2['items'], list)
    assert len(page2['items']) == 10
