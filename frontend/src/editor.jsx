import React, { useCallback, useState, useEffect, useRef } from 'react'
// react-flow-renderer v10 exports from 'react-flow-renderer'. The project
// depends on the v10 package (react-flow-renderer) rather than the newer
// renamed package (reactflow). Import from the installed package so Vite/Rollup
// can resolve the module during the build.
import ReactFlow, { addEdge, Background, Controls, ReactFlowProvider, applyNodeChanges, applyEdgeChanges } from 'react-flow-renderer'
import NodeRenderer from './NodeRenderer'

const initialNodes = [
  {
    id: '1',
    type: 'input',
    data: { label: 'Webhook Trigger' },
    position: { x: 250, y: 5 },
  },
]
const initialEdges = []

export default function Editor(){
  const [nodes, setNodes] = useState(initialNodes)
  const [edges, setEdges] = useState(initialEdges)
  const [token, setToken] = useState(localStorage.getItem('authToken') || '')
  const [workflowId, setWorkflowId] = useState(null)
  const [workflows, setWorkflows] = useState([])
  const [runs, setRuns] = useState([])
  const [selectedRunLogs, setSelectedRunLogs] = useState([])
  const [logEventSource, setLogEventSource] = useState(null)
  // keep a ref to the EventSource so we can always close it without
  // relying on state being immediately updated during the same render
  const logEventSourceRef = useRef(null)
  const [secrets, setSecrets] = useState([])
  const [providers, setProviders] = useState([])
  const [newSecretName, setNewSecretName] = useState('')
  const [newSecretValue, setNewSecretValue] = useState('')
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [workflowName, setWorkflowName] = useState('New Workflow')
  const [newProviderType, setNewProviderType] = useState('openai')
  const [newProviderSecretId, setNewProviderSecretId] = useState('')
  const [webhookTestPayload, setWebhookTestPayload] = useState('{}')

  // Run detail state
  const [selectedRunDetail, setSelectedRunDetail] = useState(null)
  const [runDetailError, setRunDetailError] = useState(null)
  const [loadingRunDetail, setLoadingRunDetail] = useState(false)

  // react-flow instance ref to compute projected coords and other helpers
  const reactFlowInstance = useRef(null)

  useEffect(() => {
    localStorage.setItem('authToken', token)
  }, [token])

  // When token becomes available, load user-scoped resources
  useEffect(() => {
    if (token) {
      loadProviders()
      loadSecrets()
      loadWorkflows()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const authHeaders = () => {
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    return headers
  }

  const loadSecrets = async () => {
    try {
      const resp = await fetch('/api/secrets', { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        setSecrets(data || [])
      }
    } catch (err) {
      // network error — keep UI responsive
      console.warn('Failed to load secrets', err)
    }
  }

  const loadProviders = async () => {
    try {
      const resp = await fetch('/api/providers', { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        setProviders(data || [])
      }
    } catch (err) {
      console.warn('Failed to load providers', err)
    }
  }

  const createSecret = async () => {
    if (!newSecretName || !newSecretValue) return alert('name and value required')
    const payload = { name: newSecretName, value: newSecretValue }
    try {
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
    } catch (err) {
      alert('Failed to create secret: ' + String(err))
    }
  }

  const createProvider = async () => {
    if (!newProviderType) return alert('provider type required')
    const payload = { type: newProviderType, config: {}, secret_id: newProviderSecretId ? Number(newProviderSecretId) : undefined }
    try {
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
    } catch (err) {
      alert('Failed to create provider: ' + String(err))
    }
  }

  const onNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), [])
  const onEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), [])

  const onConnect = useCallback((params) => setEdges((eds) => addEdge(params, eds)), [])

  // Generic addNode helper tries to compute a sensible position using the reactflow instance when available.
  // Also marks the newly created node as selected and clears selection on other nodes so the UI reflects
  // the selection immediately.
  const addNode = ({ label = 'Node', config = {}, preferY = 120 }) => {
    // Use functional update to avoid closure issues and ensure id uniqueness
    setNodes((prevNodes) => {
      // generate a compact, mostly-unique id suitable for the canvas
      const now = Date.now()
      let id = `node-${now.toString(36)}-${Math.random().toString(36).slice(2, 8)}`
      while (prevNodes.some((n) => String(n.id) === String(id))) {
        id = `node-${now.toString(36)}-${Math.random().toString(36).slice(2, 8)}`
      }

      let position = { x: (prevNodes.length * 120) % 800, y: preferY }
      try {
        if (reactFlowInstance.current && typeof reactFlowInstance.current.project === 'function') {
          const screenX = window.innerWidth / 2
          const screenY = window.innerHeight / 2
          const p = reactFlowInstance.current.project({ x: screenX, y: screenY })
          position = { x: p.x + (prevNodes.length * 20), y: p.y + preferY }
        }
      } catch (err) {
        // ignore and fall back to grid
      }

      const node = {
        id,
        type: label === 'Webhook Trigger' ? 'input' : 'default',
        // ensure a well-formed data object — other parts of the editor assume
        // data and data.config exist
        data: { label, config: config || {} },
        position,
        selected: true,
      }

      console.debug('editor:add_node', { type: label.toLowerCase(), id })

      // Update nodes: clear selection on existing nodes and append the new selected node.
      const cleared = prevNodes.map((n) => (n.selected ? { ...n, selected: false } : n))
      // schedule selectedNodeId update after state change
      // (we still return the new array here)
      setTimeout(() => setSelectedNodeId(id), 0)
      return cleared.concat(node)
    })
  }

  const addHttpNode = () => {
    addNode({ label: 'HTTP Request', config: { method: 'GET', url: '', headers: {}, body: '' }, preferY: 100 })
  }

  const addLlmNode = () => {
    const defaultProvider = providers.length > 0 ? providers[0].id : null
    addNode({ label: 'LLM', config: { prompt: '', provider_id: defaultProvider }, preferY: 200 })
  }

  const addWebhookTrigger = () => {
    addNode({ label: 'Webhook Trigger', config: {}, preferY: 20 })
  }

  const updateNodeConfig = (nodeId, newConfig) => {
    // be defensive: node data may be missing or malformed; find node and
    // merge/replace its config safely
    setNodes((nds) => nds.map((n) => {
      if (String(n.id) !== String(nodeId)) return n
      const prevData = n.data && typeof n.data === 'object' ? n.data : {}
      // ensure prevData.config is an object
      const prevConfig = prevData.config && typeof prevData.config === 'object' ? prevData.config : {}
      const merged = { ...prevData, config: { ...prevConfig, ...(newConfig || {}) } }
      return { ...n, data: merged }
    }))
  }

  const saveWorkflow = async () => {
    const payload = {
      name: workflowName || 'Untitled',
      // persist selection so editor state (selected node) can be restored
      graph: { nodes, edges, selected_node_id: selectedNodeId },
    }
    try {
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
    } catch (err) {
      alert('Save failed: ' + String(err))
    }
  }

  const loadWorkflows = async () => {
    try {
      const resp = await fetch('/api/workflows', { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        setWorkflows(data || [])
        if (data && data.length > 0) {
          const wf = data[0]
          setWorkflowId(wf.id)
          if (wf.graph) {
            if (Array.isArray(wf.graph)) {
              // legacy: array of elements
              const nodesLoaded = wf.graph.filter(e => !e.source && !e.target)
              const edgesLoaded = wf.graph.filter(e => e.source && e.target)
              // sanitize loaded nodes/edges
              const sanitize = (n) => ({
                id: String(n.id),
                type: n.type || (n.data && n.data.label === 'Webhook Trigger' ? 'input' : 'default'),
                position: n.position || { x: 0, y: 0 },
                selected: !!n.selected,
                data: n.data && typeof n.data === 'object' ? { ...n.data, config: (n.data.config || {}) } : { label: n.data && n.data.label ? n.data.label : 'Node', config: {} },
              })
              setNodes(nodesLoaded.map(sanitize))
              setEdges((edgesLoaded || []).map(e => ({ ...e, id: e.id ? String(e.id) : `${e.source}-${e.target}`, source: String(e.source), target: String(e.target) })))
              // clear selection for legacy flows (no persisted selection)
              setSelectedNodeId(null)
            } else if (wf.graph.nodes) {
              // sanitize nodes/edges coming from the server so the editor
              // does not break if fields are missing or ids are numbers
              const sanitize = (n) => ({
                id: String(n.id),
                type: n.type || (n.data && n.data.label === 'Webhook Trigger' ? 'input' : 'default'),
                position: n.position || { x: 0, y: 0 },
                selected: !!n.selected,
                data: n.data && typeof n.data === 'object' ? { ...n.data, config: (n.data.config || {}) } : { label: n.data && n.data.label ? n.data.label : 'Node', config: {} },
              })
              setNodes((wf.graph.nodes || []).map(sanitize))
              setEdges(((wf.graph.edges || [])).map(e => ({ ...e, id: e.id ? String(e.id) : `${e.source}-${e.target}`, source: String(e.source), target: String(e.target) })))
              // restore selected node if saved
              if (wf.graph.selected_node_id) {
                // ensure the selected id exists in the loaded nodes
                const exists = ((wf.graph.nodes || []).map(n => String(n.id))).includes(String(wf.graph.selected_node_id))
                setSelectedNodeId(exists ? String(wf.graph.selected_node_id) : null)
              } else {
                setSelectedNodeId(null)
              }
            }
          }
        }
      } else {
        const txt = await resp.text()
        alert('Failed to load workflows: ' + txt)
      }
    } catch (err) {
      alert('Failed to load workflows: ' + String(err))
    }
  }

  const runWorkflow = async () => {
    if (!workflowId) return alert('No workflow selected/saved')
    try {
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
    } catch (err) {
      alert('Run failed: ' + String(err))
    }
  }

  const loadRuns = async () => {
    if (!workflowId) return
    const url = `/api/runs?workflow_id=${workflowId}`
    try {
      const resp = await fetch(url, { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        setRuns(data || [])
      }
    } catch (err) {
      console.warn('Failed to load runs', err)
    }
  }

  const viewRunLogs = async (runId) => {
    // Fetch existing logs first
    try {
      const resp = await fetch(`/api/runs/${runId}/logs`, { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        // backend returns { logs: [...] }
        setSelectedRunLogs((data && data.logs) || [])
      } else {
        const txt = await resp.text()
        alert('Failed to load logs: ' + txt)
        return
      }
    } catch (err) {
      alert('Failed to load logs: ' + String(err))
      return
    }

    // Close any existing EventSource and clear refs/state so multiple
    // viewRunLogs calls don't leak event sources.
    try {
      if (logEventSourceRef.current) {
        try { logEventSourceRef.current.close() } catch (e) {}
      }
    } catch (e) {}
    logEventSourceRef.current = null
    setLogEventSource(null)

    // Start SSE to stream new logs. If a token is available include it as a
    // query param, otherwise open the stream without the token so tests and
    // unauthenticated setups can still receive events (the backend may accept
    // cookies or unauthenticated connections for streaming).
    try {
      const url = token ? `/api/runs/${runId}/stream?access_token=${token}` : `/api/runs/${runId}/stream`
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
        logEventSourceRef.current = null
        setLogEventSource(null)
      }
      logEventSourceRef.current = es
      setLogEventSource(es)
    } catch (err) {
      // EventSource may not be available in some environments; ignore
    }
  }

  const stopViewingLogs = () => {
    try {
      if (logEventSourceRef.current) {
        logEventSourceRef.current.close()
      }
    } catch (e) {}
    logEventSourceRef.current = null
    setLogEventSource(null)
  }

  const viewRunDetail = async (runId) => {
    setSelectedRunDetail(null)
    setRunDetailError(null)
    setLoadingRunDetail(true)
    try {
      const resp = await fetch(`/api/runs/${runId}`, { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        setSelectedRunDetail(data)
      } else if (resp.status === 404) {
        setRunDetailError('Run not found')
      } else {
        const txt = await resp.text()
        setRunDetailError(`Failed to load run: ${txt}`)
      }
    } catch (err) {
      setRunDetailError(String(err))
    } finally {
      setLoadingRunDetail(false)
    }
  }

  const closeRunDetail = () => {
    setSelectedRunDetail(null)
    setRunDetailError(null)
  }

  const onNodeClick = (event, node) => {
    if (!node || !node.id) return
    setSelectedNodeId(node.id)
  }

  const onPaneClick = () => {
    setSelectedNodeId(null)
  }

  useEffect(() => {
    // initial load of providers and secrets only when token present
    if (token) {
      loadProviders()
      loadSecrets()
      loadWorkflows()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      try {
        if (logEventSourceRef.current) {
          logEventSourceRef.current.close()
        }
      } catch (e) {}
      logEventSourceRef.current = null
      setLogEventSource(null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logEventSource])

  const selectedNode = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) : null

  const copyWebhookUrl = () => {
    if (!workflowId || !selectedNodeId) return alert('Save the workflow and select the webhook node to get a URL')
    const url = `${window.location.origin}/api/webhook/${workflowId}/${selectedNodeId}`
    navigator.clipboard && navigator.clipboard.writeText(url)
    alert('Webhook URL copied to clipboard: ' + url)
  }

  const testWebhook = async () => {
    if (!workflowId || !selectedNodeId) return alert('Save the workflow and select the webhook node to test')
    let payload = {}
    try {
      payload = JSON.parse(webhookTestPayload || '{}')
    } catch (e) {
      return alert('Invalid JSON payload')
    }
    try {
      const resp = await fetch(`/api/webhook/${workflowId}/${selectedNodeId}`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(payload),
      })
      if (resp.ok) {
        const data = await resp.json()
        alert('Webhook test queued run_id: ' + data.run_id)
        await loadRuns()
        if (data && data.run_id) viewRunLogs(data.run_id)
      } else {
        const txt = await resp.text()
        alert('Webhook test failed: ' + txt)
      }
    } catch (err) {
      alert('Webhook test failed: ' + String(err))
    }
  }

  const safeStringify = (v) => {
    try {
      if (v === undefined) return 'undefined'
      if (v === null) return 'null'
      if (typeof v === 'string') return v
      return JSON.stringify(v, null, 2)
    } catch (e) {
      return String(v)
    }
  }

  return (
    <div className="editor-root">
      <div className="editor-main">
        <div className="sidebar">
          <h3>Palette</h3>
          <div className="palette-buttons">
            <button onClick={addHttpNode}>Add HTTP Node</button>
            <button onClick={addLlmNode}>Add LLM Node</button>
            <button onClick={addWebhookTrigger}>Add Webhook</button>
          </div>
          <hr />
          <div>
            <strong>Auth Token (dev):</strong>
            <input value={token} onChange={(e) => setToken(e.target.value)} placeholder='Paste bearer token here' />
          </div>

          <hr />
          <div className="row">
            <input className="col" value={workflowName} onChange={(e) => setWorkflowName(e.target.value)} />
            <button onClick={saveWorkflow}>Save</button>
          </div>
          <div className="mt-8">Selected workflow id: {workflowId || 'none'}</div>
          <div className="row mt-8">
            <button onClick={loadWorkflows}>Load</button>
            <button onClick={runWorkflow}>Run</button>
            <button onClick={loadRuns}>Refresh Runs</button>
          </div>

          <hr />
          <h4>Providers</h4>
          <div className="row" style={{ marginBottom: 6 }}>
            <input placeholder='Type (e.g. openai)' value={newProviderType} onChange={(e) => setNewProviderType(e.target.value)} style={{ width: '60%', marginRight: 6 }} />
            <select value={newProviderSecretId} onChange={(e) => setNewProviderSecretId(e.target.value)} style={{ width: '30%', marginRight: 6 }}>
              <option value=''>No secret</option>
              {secrets.map(s => <option key={s.id} value={s.id}>{s.name} (id:{s.id})</option>)}
            </select>
            <button onClick={createProvider}>Create Provider</button>
          </div>

          <div className="list-scroll">
            {providers.length === 0 ? <div className="muted">No providers</div> : providers.map(p => (
              <div key={p.id} className="list-item">
                <div><strong>{p.type}</strong> <span className="muted">(id: {p.id})</span></div>
              </div>
            ))}
          </div>

          <hr />
          <h4>Secrets</h4>
          <div style={{ marginBottom: 8 }}>
            <button onClick={loadSecrets}>Refresh Secrets</button>
          </div>
          <div className="list-scroll">
            {secrets.length === 0 ? <div className="muted">No secrets</div> : secrets.map(s => (
              <div key={s.id} className="list-item">
                <div><strong>{s.name}</strong></div>
                <div className="muted">id: {s.id} <button onClick={() => { navigator.clipboard && navigator.clipboard.writeText(String(s.id)); alert('Copied id to clipboard') }} className="secondary">Copy id</button></div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 8 }}>
            <input placeholder='Secret name' value={newSecretName} onChange={(e) => setNewSecretName(e.target.value)} style={{ marginBottom: 6 }} />
            <input placeholder='Secret value' value={newSecretValue} onChange={(e) => setNewSecretValue(e.target.value)} style={{ marginBottom: 6 }} />
            <button onClick={createSecret}>Create Secret</button>
          </div>

          <h4 style={{ marginTop: 12 }}>Runs</h4>
          <div className="list-scroll runs-list">
            {runs.length === 0 ? <div className="muted">No runs</div> : runs.map(r => (
              <div key={r.id} className="run-item">
                <div className="run-meta">Run {r.id} — {r.status}</div>
                <div>
                  <button onClick={() => viewRunLogs(r.id)} className="secondary">View Logs</button>
                  <button onClick={() => viewRunDetail(r.id)} style={{ marginLeft: 6 }} className="secondary">Details</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="canvas">
          <div style={{ flex: 1 }} className="reactflow-wrapper">
            <ReactFlowProvider>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                nodeTypes={{ default: NodeRenderer }}
                onInit={(instance) => { reactFlowInstance.current = instance }}
              >
                <Background />
                <Controls />
              </ReactFlow>
            </ReactFlowProvider>
          </div>
        </div>

        <div className="rightpanel">
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

                  <div style={{ fontSize: 12, color: 'var(--muted)' }}>Note: live LLM calls are disabled by default in the backend. Enable via environment flag to make real API calls.</div>
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
                      setNodes((nds) => nds.map(n => n.id === selectedNodeId ? { ...n, data: parsed } : n))
                    } catch (err) {
                      // ignore
                    }
                  }} />
                </div>
              )}

            </div>
          ) : (
            <div className="muted">No node selected. Click a node to view/edit its config.</div>
          )}

          <hr />
          <h3>Run Details</h3>
          <div style={{ maxHeight: '40vh', overflow: 'auto', marginBottom: 8 }}>
            {loadingRunDetail ? (
              <div className="muted">Loading...</div>
            ) : runDetailError ? (
              <div className="muted">{runDetailError}</div>
            ) : selectedRunDetail ? (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div><strong>Run {selectedRunDetail.id}</strong> — {selectedRunDetail.status}</div>
                  <div><button onClick={closeRunDetail} className="secondary">Close</button></div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>
                  Workflow: {selectedRunDetail.workflow_id} — Attempts: {selectedRunDetail.attempts}
                </div>
                <div style={{ marginTop: 8 }}>
                  <div><strong>Input</strong></div>
                  <pre style={{ whiteSpace: 'pre-wrap' }}>{safeStringify(selectedRunDetail.input)}</pre>
                </div>
                <div style={{ marginTop: 8 }}>
                  <div><strong>Output</strong></div>
                  <pre style={{ whiteSpace: 'pre-wrap' }}>{safeStringify(selectedRunDetail.output)}</pre>
                </div>
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)' }}>
                  Created: {selectedRunDetail.created_at || 'n/a'} — Started: {selectedRunDetail.started_at || 'n/a'} — Finished: {selectedRunDetail.finished_at || 'n/a'}
                </div>
                <hr />
                <div><strong>Logs</strong></div>
                {selectedRunDetail.logs && selectedRunDetail.logs.length > 0 ? selectedRunDetail.logs.map(l => (
                  <div key={l.id} className="log-entry">
                    <div style={{ fontSize: 12, color: 'var(--muted)' }}>{l.timestamp} — {l.node_id} — {l.level}</div>
                    <pre>{typeof l.message === 'string' ? l.message : JSON.stringify(l.message, null, 2)}</pre>
                  </div>
                )) : <div className="muted">No logs for this run</div>}
              </div>
            ) : (
              <div className="muted">No run selected. Click "Details" in the runs list to load a run.</div>
            )}
          </div>

          <hr />
          <h3>Selected Run Logs</h3>
          <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
            {selectedRunLogs.length === 0 ? <div className="muted">No logs selected</div> : selectedRunLogs.map(l => (
              <div key={l.id} className="log-entry">
                <div style={{ fontSize: 12, color: 'var(--muted)' }}>{l.timestamp} — {l.node_id} — {l.level}</div>
                <pre>{typeof l.message === 'string' ? l.message : JSON.stringify(l.message, null, 2)}</pre>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
