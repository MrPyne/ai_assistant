import React, { useCallback, useState, useEffect } from 'react'
import ReactFlow, { addEdge, Background, Controls } from 'react-flow-renderer'
import NodeRenderer from './NodeRenderer'

const initialElements = [
  {
    id: '1',
    type: 'input',
    data: { label: 'Webhook Trigger' },
    position: { x: 250, y: 5 },
  },
]

export default function Editor(){
  const [elements, setElements] = useState(initialElements)
  const [token, setToken] = useState(localStorage.getItem('authToken') || '')
  const [workflowId, setWorkflowId] = useState(null)
  const [workflows, setWorkflows] = useState([])
  const [runs, setRuns] = useState([])
  const [selectedRunLogs, setSelectedRunLogs] = useState([])
  const [logEventSource, setLogEventSource] = useState(null)
  const [secrets, setSecrets] = useState([])
  const [providers, setProviders] = useState([])
  const [newSecretName, setNewSecretName] = useState('')
  const [newSecretValue, setNewSecretValue] = useState('')
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [workflowName, setWorkflowName] = useState('New Workflow')
  const [newProviderType, setNewProviderType] = useState('openai')
  const [newProviderSecretId, setNewProviderSecretId] = useState('')

  useEffect(() => {
    localStorage.setItem('authToken', token)
  }, [token])

  const authHeaders = () => {
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    return headers
  }

  const loadSecrets = async () => {
    const resp = await fetch('/api/secrets', { headers: authHeaders() })
    if (resp.ok) {
      const data = await resp.json()
      setSecrets(data || [])
    }
  }

  const loadProviders = async () => {
    const resp = await fetch('/api/providers', { headers: authHeaders() })
    if (resp.ok) {
      const data = await resp.json()
      setProviders(data || [])
    }
  }

  const createSecret = async () => {
    if (!newSecretName || !newSecretValue) return alert('name and value required')
    const payload = { name: newSecretName, value: newSecretValue }
    const resp = await fetch('/api/secrets', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
    if (resp.ok) {
      alert('Secret created')
      setNewSecretName('')
      setNewSecretValue('')
      await loadSecrets()
    } else {
      const txt = await resp.text()
      alert('Failed to create secret: ' + txt)
    }
  }

  const createProvider = async () => {
    if (!newProviderType) return alert('provider type required')
    const payload = { type: newProviderType, config: {}, secret_id: newProviderSecretId ? Number(newProviderSecretId) : undefined }
    const resp = await fetch('/api/providers', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
    if (resp.ok) {
      alert('Provider created')
      setNewProviderSecretId('')
      await loadProviders()
    } else {
      const txt = await resp.text()
      alert('Failed to create provider: ' + txt)
    }
  }

  const onConnect = useCallback((params) => setElements((els) => addEdge(params, els)), [])

  const addHttpNode = () => {
    const id = String(Date.now())
    const newNode = {
      id,
      type: 'default',
      data: { label: 'HTTP Request', config: { method: 'GET', url: '', headers: {}, body: '' } },
      position: { x: (elements.length * 120) % 800, y: 100 },
    }
    setElements((els) => els.concat(newNode))
  }

  const addLlmNode = () => {
    const id = String(Date.now())
    const defaultProvider = providers.length > 0 ? providers[0].id : null
    const newNode = {
      id,
      type: 'default',
      data: { label: 'LLM', config: { prompt: '', provider_id: defaultProvider } },
      position: { x: (elements.length * 120) % 800, y: 200 },
    }
    setElements((els) => els.concat(newNode))
  }

  const addWebhookTrigger = () => {
    const id = String(Date.now())
    const newNode = {
      id,
      type: 'input',
      data: { label: 'Webhook Trigger', config: {} },
      position: { x: (elements.length * 120) % 800, y: 20 },
    }
    setElements((els) => els.concat(newNode))
  }

  const updateNodeConfig = (nodeId, newConfig) => {
    setElements((els) => els.map(e => (
      e.id === nodeId ? { ...e, data: { ...e.data, config: newConfig } } : e
    )))
  }

  const saveWorkflow = async () => {
    const payload = {
      name: workflowName || 'Untitled',
      graph: { nodes: elements },
    }
    const resp = await fetch('/api/workflows', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
    if (resp.ok) {
      const data = await resp.json()
      alert('Saved')
      if (data && data.id) setWorkflowId(data.id)
    } else {
      const txt = await resp.text()
      alert('Save failed: ' + txt)
    }
  }

  const loadWorkflows = async () => {
    const resp = await fetch('/api/workflows', { headers: authHeaders() })
    if (resp.ok) {
      const data = await resp.json()
      setWorkflows(data || [])
      if (data && data.length > 0) {
        const wf = data[0]
        setWorkflowId(wf.id)
        if (wf.graph) {
          if (Array.isArray(wf.graph)) setElements(wf.graph)
          else if (wf.graph.nodes) setElements(wf.graph.nodes)
        }
      }
    } else {
      alert('Failed to load workflows')
    }
  }

  const runWorkflow = async () => {
    if (!workflowId) return alert('No workflow selected/saved')
    const resp = await fetch(`/api/workflows/${workflowId}/run`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({}),
    })
    if (resp.ok) {
      const data = await resp.json()
      alert('Run queued: ' + data.run_id)
      await loadRuns()
      // Automatically open streaming logs for the new run
      if (data && data.run_id) {
        viewRunLogs(data.run_id)
      }
    } else {
      const txt = await resp.text()
      alert('Run failed: ' + txt)
    }
  }

  const loadRuns = async () => {
    if (!workflowId) return
    const url = `/api/runs?workflow_id=${workflowId}`
    const resp = await fetch(url, { headers: authHeaders() })
    if (resp.ok) {
      const data = await resp.json()
      setRuns(data || [])
    }
  }

  const viewRunLogs = async (runId) => {
    // Fetch existing logs first
    const resp = await fetch(`/api/runs/${runId}/logs`, { headers: authHeaders() })
    if (resp.ok) {
      const data = await resp.json()
      setSelectedRunLogs(data || [])
    } else {
      alert('Failed to load logs')
      return
    }

    // Close any existing EventSource
    if (logEventSource) {
      try {
        logEventSource.close()
      } catch (e) {}
      setLogEventSource(null)
    }

    // Start SSE to stream new logs (uses access_token query param for EventSource)
    if (!token) return
    try {
      const url = `/api/runs/${runId}/stream?access_token=${token}`
      const es = new EventSource(url)
      es.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data)
          setSelectedRunLogs((prev) => prev.concat([payload]))
        } catch (err) {
          // ignore parse errors
        }
      }
      es.onerror = (err) => {
        // If the connection closes or errors, close and clear the source
        try { es.close() } catch (e) {}
        setLogEventSource(null)
      }
      setLogEventSource(es)
    } catch (err) {
      // EventSource may not be available in some environments; ignore
    }
  }

  const onElementClick = (event, element) => {
    if (!element || !element.id) return
    setSelectedNodeId(element.id)
  }

  const onPaneClick = () => {
    setSelectedNodeId(null)
  }

  useEffect(() => {
    // initial load of providers and secrets
    loadProviders()
    loadSecrets()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (logEventSource) {
        try { logEventSource.close() } catch (e) {}
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logEventSource])

  const selectedNode = selectedNodeId ? elements.find(e => e.id === selectedNodeId) : null

  const copyWebhookUrl = () => {
    if (!workflowId || !selectedNodeId) return alert('Save the workflow and select the webhook node to get a URL')
    const url = `${window.location.origin}/api/webhook/${workflowId}/${selectedNodeId}`
    navigator.clipboard && navigator.clipboard.writeText(url)
    alert('Webhook URL copied to clipboard: ' + url)
  }

  return (
    <div style={{ height: '100vh', display: 'flex' }}>
      <div style={{ width: 320, padding: 10, borderRight: '1px solid #eee' }}>
        <h3>Palette</h3>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={addHttpNode}>Add HTTP Node</button>
          <button onClick={addLlmNode}>Add LLM Node</button>
          <button onClick={addWebhookTrigger}>Add Webhook</button>
        </div>
        <hr />
        <div>
          <strong>Auth Token (dev):</strong>
          <input style={{ width: '100%' }} value={token} onChange={(e) => setToken(e.target.value)} placeholder='Paste bearer token here' />
        </div>
        <hr />
        <div style={{ display: 'flex', gap: 6 }}>
          <input style={{ flex: 1 }} value={workflowName} onChange={(e) => setWorkflowName(e.target.value)} />
          <button onClick={saveWorkflow}>Save</button>
        </div>
        <div style={{ marginTop: 8 }}>Selected workflow id: {workflowId || 'none'}</div>
        <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
          <button onClick={loadWorkflows}>Load</button>
          <button onClick={runWorkflow}>Run</button>
          <button onClick={loadRuns}>Refresh Runs</button>
        </div>

        <hr />
        <h4>Providers</h4>
        <div style={{ marginBottom: 6 }}>
          <input placeholder='Type (e.g. openai)' value={newProviderType} onChange={(e) => setNewProviderType(e.target.value)} style={{ width: '60%', marginRight: 6 }} />
          <select value={newProviderSecretId} onChange={(e) => setNewProviderSecretId(e.target.value)} style={{ width: '30%', marginRight: 6 }}>
            <option value=''>No secret</option>
            {secrets.map(s => <option key={s.id} value={s.id}>{s.name} (id:{s.id})</option>)}
          </select>
          <button onClick={createProvider}>Create Provider</button>
        </div>

        <div style={{ maxHeight: 120, overflow: 'auto', border: '1px solid #ddd', padding: 6 }}>
          {providers.length === 0 ? <div style={{ color: '#666' }}>No providers</div> : providers.map(p => (
            <div key={p.id} style={{ padding: 6, borderBottom: '1px solid #f6f6f6' }}>
              <div><strong>{p.type}</strong> <span style={{ fontSize: 12, color: '#666' }}>(id: {p.id})</span></div>
            </div>
          ))}
        </div>

        <hr />
        <h4>Secrets</h4>
        <div style={{ marginBottom: 8 }}>
          <button onClick={loadSecrets}>Refresh Secrets</button>
        </div>
        <div style={{ maxHeight: 120, overflow: 'auto', border: '1px solid #ddd', padding: 6 }}>
          {secrets.length === 0 ? <div style={{ color: '#666' }}>No secrets</div> : secrets.map(s => (
            <div key={s.id} style={{ padding: 6, borderBottom: '1px solid #f6f6f6' }}>
              <div><strong>{s.name}</strong></div>
              <div style={{ fontSize: 12, color: '#666' }}>id: {s.id} <button onClick={() => { navigator.clipboard && navigator.clipboard.writeText(String(s.id)); alert('Copied id to clipboard') }}>Copy id</button></div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 8 }}>
          <input placeholder='Secret name' value={newSecretName} onChange={(e) => setNewSecretName(e.target.value)} style={{ width: '100%', marginBottom: 6 }} />
          <input placeholder='Secret value' value={newSecretValue} onChange={(e) => setNewSecretValue(e.target.value)} style={{ width: '100%', marginBottom: 6 }} />
          <button onClick={createSecret}>Create Secret</button>
        </div>

        <h4 style={{ marginTop: 12 }}>Runs</h4>
        <div style={{ maxHeight: 180, overflow: 'auto', border: '1px solid #ddd', padding: 4 }}>
          {runs.length === 0 ? <div style={{ color: '#666' }}>No runs</div> : runs.map(r => (
            <div key={r.id} style={{ padding: 6, borderBottom: '1px solid #f0f0f0' }}>
              <div style={{ fontSize: 13 }}>Run {r.id} — {r.status}</div>
              <div style={{ marginTop: 6 }}>
                <button onClick={() => viewRunLogs(r.id)}>View Logs</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ flex: 1 }}>
        <ReactFlow
          elements={elements}
          onConnect={onConnect}
          onElementClick={onElementClick}
          onPaneClick={onPaneClick}
          nodeTypes={{ default: NodeRenderer }}
        />
        <Background />
        <Controls />
      </div>

      <div style={{ width: 380, padding: 10, borderLeft: '1px solid #eee' }}>
        <h3>Selected Node</h3>
        {selectedNode ? (
          <div>
            <div style={{ marginBottom: 8 }}>Node id: <strong>{selectedNodeId}</strong></div>

            {/* Webhook info */}
            {selectedNode.data && selectedNode.data.label === 'Webhook Trigger' && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ marginBottom: 6 }}>Webhook trigger node.</div>
                <div style={{ fontSize: 13, marginBottom: 6 }}>After saving the workflow, copy the webhook URL and POST to it to trigger a run.</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={copyWebhookUrl}>Copy webhook URL</button>
                  <button onClick={() => { if (workflowId && selectedNodeId) { const url = `${window.location.origin}/api/webhook/${workflowId}/${selectedNodeId}`; window.open(url, '_blank') } else { alert('Save the workflow first') } }}>Open (GET)</button>
                </div>
              </div>
            )}

            {/* HTTP Node Config */}
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
                    // ignore parse errors while typing
                  }
                }} />

                <label>Body</label>
                <textarea style={{ width: '100%', height: 80 }} value={(selectedNode.data.config && selectedNode.data.config.body) || ''} onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), body: e.target.value })} />

              </div>
            )}

            {/* LLM Node Config */}
            {selectedNode.data && selectedNode.data.label === 'LLM' && (
              <div>
                <label>Prompt</label>
                <textarea style={{ width: '100%', height: 140, marginBottom: 8 }} value={(selectedNode.data.config && selectedNode.data.config.prompt) || ''} onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), prompt: e.target.value })} />

                <label>Provider</label>
                <select value={(selectedNode.data.config && selectedNode.data.config.provider_id) || ''} onChange={(e) => updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), provider_id: e.target.value ? Number(e.target.value) : null })} style={{ width: '100%', marginBottom: 8 }}>
                  <option value=''>-- Select provider --</option>
                  {providers.map(p => <option key={p.id} value={p.id}>{p.type} (id:{p.id})</option>)}
                </select>

                <div style={{ fontSize: 12, color: '#666' }}>Note: live LLM calls are disabled by default in the backend. Enable via environment flag to make real API calls.</div>
              </div>
            )}

            {/* Fallback raw JSON editor for other node types */}
            {(!selectedNode.data || (selectedNode.data && !['HTTP Request', 'LLM', 'Webhook Trigger'].includes(selectedNode.data.label))) && (
              <div>
                <label>Raw node config (JSON)</label>
                <textarea style={{ width: '100%', height: 240 }} value={JSON.stringify(selectedNode.data || {}, null, 2)} onChange={(e) => {
                  try {
                    const parsed = JSON.parse(e.target.value)
                    // replace entire data
                    setElements((els) => els.map(el => el.id === selectedNodeId ? { ...el, data: parsed } : el))
                  } catch (err) {
                    // ignore
                  }
                }} />
              </div>
            )}

          </div>
        ) : (
          <div style={{ color: '#666' }}>No node selected. Click a node to view/edit its config.</div>
        )}

        <hr />
        <h3>Selected Run Logs</h3>
        <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
          {selectedRunLogs.length === 0 ? <div style={{ color: '#666' }}>No logs selected</div> : selectedRunLogs.map(l => (
            <div key={l.id} style={{ marginBottom: 8, padding: 6, border: '1px solid #eee' }}>
              <div style={{ fontSize: 12, color: '#666' }}>{l.timestamp} — {l.node_id} — {l.level}</div>
              <pre style={{ whiteSpace: 'pre-wrap' }}>{typeof l.message === 'string' ? l.message : JSON.stringify(l.message, null, 2)}</pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
