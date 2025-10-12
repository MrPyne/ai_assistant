import React from 'react'

export default function NodeInspector({
  selectedNode,
  selectedNodeId,
  setShowNodeTest,
  setNodeTestToken,
  token,
  copyWebhookUrl,
  workflowId,
  webhookTestPayload,
  setWebhookTestPayload,
  testWebhook,
  updateNodeConfig,
  providers,
  nodeOptions,
  autoWireTarget,
  setNodes,
  markDirty,
}) {
  if (!selectedNode) return <div className="muted">No node selected. Click a node to view/edit its config.</div>

  return (
    <div>
      <div style={{ marginBottom: 8 }}>Node id: <strong>{selectedNodeId}</strong></div>
      <div style={{ marginBottom: 8 }}>
        <button onClick={() => { setShowNodeTest(true); setNodeTestToken(token) }} className="btn btn-ghost">Test Node</button>
      </div>

      {selectedNode.data && selectedNode.data.label === 'Webhook Trigger' && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ marginBottom: 6 }}>Webhook trigger node.</div>
          <div style={{ fontSize: 13, marginBottom: 6 }}>After saving the workflow, copy the webhook URL and POST to it to trigger a run.</div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={copyWebhookUrl}>Copy webhook URL</button>
            <button onClick={() => { if (workflowId && selectedNodeId) { const url = `${window.location.origin}/api/webhook/${workflowId}/${selectedNodeId}`; window.open(url, '_blank') } else { alert('Save the workflow first') } }} className="secondary">Open (GET)</button>
          </div>

          <div style={{ marginTop: 8 }}>
            <label style={{ display: 'block', marginBottom: 4 }}>Test payload (JSON)</label>
            <textarea value={webhookTestPayload} onChange={(e) => setWebhookTestPayload(e.target.value)} style={{ width: '100%', height: 120 }} />
            <div style={{ marginTop: 6, display: 'flex', gap: 6 }}>
              <button onClick={testWebhook}>Send Test (POST)</button>
              <button onClick={() => { setWebhookTestPayload('{}') }} className="secondary">Reset</button>
            </div>
          </div>
        </div>
      )}

      {selectedNode.data && selectedNode.data.label === 'HTTP Request' && (
        <div>
          <label>Method</label>
          <select value={(selectedNode.data.config && selectedNode.data.config.method) || 'GET'} onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), method: e.target.value })} style={{ width: '100%', marginBottom: 8 }}>
            <option>GET</option>
            <option>POST</option>
            <option>PUT</option>
            <option>DELETE</option>
            <option>PATCH</option>
          </select>

          <label>URL</label>
          <input style={{ width: '100%', marginBottom: 8 }} value={(selectedNode.data.config && selectedNode.data.config.url) || ''} onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), url: e.target.value })} />

          <label>Headers (JSON)</label>
          <textarea style={{ width: '100%', height: 80, marginBottom: 8 }} value={JSON.stringify((selectedNode.data.config && selectedNode.data.config.headers) || {}, null, 2)} onChange={(e) => {
            try {
              const parsed = JSON.parse(e.target.value || '{}')
              updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), headers: parsed })
            } catch (err) {
            }
          }} />

          <label>Body</label>
          <textarea style={{ width: '100%', height: 80 }} value={(selectedNode.data.config && selectedNode.data.config.body) || ''} onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), body: e.target.value })} />

        </div>
      )}

      {selectedNode.data && selectedNode.data.label === 'LLM' && (
        <div>
          <label>Prompt</label>
          <textarea style={{ width: '100%', height: 140, marginBottom: 8 }} value={(selectedNode.data.config && selectedNode.data.config.prompt) || ''} onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), prompt: e.target.value })} />

          <label>Provider</label>
          <select value={(selectedNode.data.config && selectedNode.data.config.provider_id) || ''} onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), provider_id: e.target.value ? Number(e.target.value) : null })} style={{ width: '100%', marginBottom: 8 }}>
            <option value=''>-- Select provider --</option>
            {providers.map(p => <option key={p.id} value={p.id}>{p.type} (id:{p.id})</option>)}
          </select>

          <div style={{ fontSize: 12, color: 'var(--muted)' }}>Note: live LLM calls are disabled by default in the backend. Enable via environment flag to make real API calls.</div>
        </div>
      )}

      {(!selectedNode.data || (selectedNode.data && !['HTTP Request', 'LLM', 'Webhook Trigger'].includes(selectedNode.data.label))) && (
        <div>
          <label>Raw node config (JSON)</label>
          <textarea style={{ width: '100%', height: 240 }} value={JSON.stringify(selectedNode.data || {}, null, 2)} onChange={(e) => {
            try {
              const parsed = JSON.parse(e.target.value)
              setNodes((nds) => nds.map(n => n.id === selectedNodeId ? { ...n, data: parsed } : n))
              markDirty()
            } catch (err) {
            }
          }} />
          {selectedNode.data && ['If', 'Switch', 'Condition'].includes(selectedNode.data.label) && (
            <div style={{ marginTop: 8 }}>
              <div style={{ marginBottom: 6 }}><strong>Auto-wire targets</strong></div>
              <div style={{ display: 'flex', gap: 6 }}>
                <select onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), true_target: e.target.value || null })} value={(selectedNode.data.config && selectedNode.data.config.true_target) || ''}>
                  <option value=''>-- true target --</option>
                  {nodeOptions(selectedNodeId).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
                </select>
                <button onClick={() => { const t = (selectedNode.data.config && selectedNode.data.config.true_target); autoWireTarget(selectedNodeId, t) }} className="secondary">Wire</button>
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                <select onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), false_target: e.target.value || null })} value={(selectedNode.data.config && selectedNode.data.config.false_target) || ''}>
                  <option value=''>-- false target --</option>
                  {nodeOptions(selectedNodeId).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
                </select>
                <button onClick={() => { const t = (selectedNode.data.config && selectedNode.data.config.false_target); autoWireTarget(selectedNodeId, t) }} className="secondary">Wire</button>
              </div>
            </div>
          )}
        </div>
      )}

    </div>
  )
}
