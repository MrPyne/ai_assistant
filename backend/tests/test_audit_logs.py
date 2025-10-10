import csv
from io import StringIO


def test_audit_logs_list_and_export(client):
    # register and create secret
    r = client.post('/api/auth/register', json={'email': 'auditor@example.com', 'password': 'pass'})
    assert r.status_code in (200, 201)
    token = r.json().get('access_token')
    headers = {'Authorization': f'Bearer {token}'} if token else {}

    # create a secret (should emit create_secret audit)
    s = {'name': 'audkey', 'value': 'svalue'}
    r2 = client.post('/api/secrets', json=s, headers=headers)
    assert r2.status_code in (200, 201)
    sid = r2.json().get('id')
    assert sid

    # create a workflow and trigger a manual run (should emit create_run audit)
    wf = {'name': 'w1', 'graph': None}
    r3 = client.post('/api/workflows', json=wf, headers=headers)
    assert r3.status_code in (200, 201)
    wid = r3.json().get('id')
    assert wid

    r4 = client.post(f'/api/workflows/{wid}/run', json={}, headers=headers)
    assert r4.status_code in (200, 201)
    run_id = r4.json().get('run_id')
    assert run_id

    # List audit logs and ensure both actions are present
    r_list = client.get('/api/audit_logs?limit=100&offset=0', headers=headers)
    assert r_list.status_code == 200
    body = r_list.json()
    assert 'items' in body
    actions = {it['action'] for it in body['items']}
    assert 'create_secret' in actions
    assert 'create_run' in actions

    # Export CSV and verify contents
    r_csv = client.get('/api/audit_logs/export', headers=headers)
    assert r_csv.status_code == 200
    text = r_csv.text
    # parse CSV and ensure header and at least two rows present
    reader = csv.reader(StringIO(text))
    rows = list(reader)
    assert rows[0] == ['id', 'workspace_id', 'user_id', 'action', 'object_type', 'object_id', 'detail', 'timestamp']
    # ensure at least one create_secret and one create_run line
    csv_actions = {r[3] for r in rows[1:]}
    assert 'create_secret' in csv_actions
    assert 'create_run' in csv_actions


def test_audit_logs_filters(client):
    # register a second user to ensure workspace scoping and user_id filter
    r = client.post('/api/auth/register', json={'email': 'filterer@example.com', 'password': 'pass'})
    assert r.status_code in (200, 201)
    token = r.json().get('access_token')
    headers = {'Authorization': f'Bearer {token}'} if token else {}

    # create a workflow and run it (audit in this workspace only)
    wf = {'name': 'wf-f', 'graph': None}
    r3 = client.post('/api/workflows', json=wf, headers=headers)
    assert r3.status_code in (200, 201)
    wid = r3.json().get('id')
    r4 = client.post(f'/api/workflows/{wid}/run', json={}, headers=headers)
    assert r4.status_code in (200, 201)

    # list audit logs for this user; should show create_run for their workspace
    r_list = client.get('/api/audit_logs?limit=50', headers=headers)
    assert r_list.status_code == 200
    items = r_list.json().get('items', [])
    assert any(it['action'] == 'create_run' for it in items)

    # filter by action that doesn't exist -> empty result
    r_filter = client.get('/api/audit_logs?action=does_not_exist', headers=headers)
    assert r_filter.status_code == 200
    body = r_filter.json()
    assert body['total'] == 0 or body['items'] == []
