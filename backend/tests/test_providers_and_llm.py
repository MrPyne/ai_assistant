def test_create_provider_and_llm_node(client):
    # create provider
    p = {"type": "openai", "config": {}}
    r = client.post('/api/providers', json=p)
    assert r.status_code in (200, 201)
    pdata = r.json()
    pid = pdata.get('id') or 1

    # provider should not expose api_key or api_key_encrypted in response
    assert 'config' not in pdata or pdata.get('config') in (None, {}, [])

    # create workflow with an LLM node referencing the provider
    wf = {
        "name": "llm-test",
        "description": "test",
        "graph": {"nodes": [{"id": "n1", "type": "llm", "provider_id": pid, "prompt": "Hello"}]}
    }
    r2 = client.post('/api/workflows', json=wf)
    assert r2.status_code in (200, 201)
    wf_json = r2.json()
    wf_id = wf_json.get('id') or wf_json.get('workflow_id') or 1

    # trigger manual run
    r3 = client.post(f'/api/workflows/{wf_id}/run', json={})
    assert r3.status_code == 200
    data = r3.json()
    assert 'run_id' in data
    run_id = data['run_id']

    # fetch run logs
    r4 = client.get(f'/api/runs/{run_id}/logs')
    assert r4.status_code == 200
