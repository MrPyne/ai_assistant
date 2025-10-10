import csv
from io import StringIO


def test_no_plaintext_secrets_in_audit_export_and_workflows(client):
    # register admin and create a secret with an obvious provider-like value
    r = client.post('/api/auth/register', json={'email': 'scanner@example.com', 'password': 'pass', 'role': 'admin'})
    assert r.status_code in (200, 201)
    token = r.json().get('access_token')
    headers = {'Authorization': f'Bearer {token}'} if token else {}

    secret_value = 'sk-SECRET_SCAN_123456'
    s = {'name': 'scan_key', 'value': secret_value}
    r2 = client.post('/api/secrets', json=s, headers=headers)
    assert r2.status_code in (200, 201)
    sid = r2.json().get('id')
    assert sid

    # create a workflow and trigger a run so an audit entry exists
    wf = {'name': 'scan-wf', 'graph': None}
    r3 = client.post('/api/workflows', json=wf, headers=headers)
    assert r3.status_code in (200, 201)
    wid = r3.json().get('id')
    assert wid

    r4 = client.post(f'/api/workflows/{wid}/run', json={}, headers=headers)
    assert r4.status_code in (200, 201)

    # Export CSV and verify secret value does not appear anywhere
    r_csv = client.get('/api/audit_logs/export', headers=headers)
    assert r_csv.status_code == 200
    text = getattr(r_csv, 'text', None) or ''
    assert secret_value not in text

    # Also ensure listing workflows and providers do not leak secret values
    r_wfs = client.get('/api/workflows', headers=headers)
    assert r_wfs.status_code == 200
    wfs_text = str(r_wfs.json())
    assert secret_value not in wfs_text

    r_prov = client.get('/api/providers', headers=headers)
    assert r_prov.status_code == 200
    prov_text = str(r_prov.json())
    assert secret_value not in prov_text
