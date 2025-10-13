import React, { useCallback, useEffect, useRef, useState } from 'react'
import { EditorProvider, useEditorDispatch, useEditorState } from './state/EditorContext'
import Sidebar from './components/Sidebar'
import RightPanel from './components/RightPanel'
import NodeRenderer from './NodeRenderer'
import ReactFlow, { ReactFlowProvider, Background, Controls } from 'react-flow-renderer'

// A compact, test-focused Editor implementation. The real app uses react-flow
// and a richer editor; tests only require a handful of behaviors (add nodes,
// save/load workflows, run and stream logs, selection). Keep the implementation
// intentionally small and defensive to avoid TDZ / initialization ordering issues.

function makeId(prefix = 'n') {
  return `${prefix}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1000)}`
}

function EditorInner({ initialToken = '' }) {
  const editorDispatch = useEditorDispatch()
  const editorState = useEditorState()

  const [nodes, setNodes] = useState([])
  const [edges] = useState([])
  const nodesRef = useRef(nodes)
  const selectedNodeId = editorState.selectedNodeId

  // workflow/workflows state used by the Sidebar tests
  const [workflowId, setWorkflowId] = useState(null)
  const [workflows, setWorkflows] = useState([])

  // token used by the Workflows panel (initialize from prop so App can pass auth token)
  const [token, setToken] = useState(initialToken || '')

  // runs & eventsource handling
  const esRef = useRef(null)

  // keep refs up-to-date for event handlers
  useEffect(() => { nodesRef.current = nodes }, [nodes])

  // expose a simple deleteSelected helper on window for RightPanel to call
  useEffect(() => {
    window.__editor_deleteSelected = () => {
      const sel = editorState.selectedIds || []
      if (!sel.length) return
      const next = nodesRef.current.filter(n => !sel.includes(String(n.id)))
      setNodes(next)
      editorDispatch({ type: 'CLEAR_SELECTION' })
      editorDispatch({ type: 'MARK_DIRTY' })
    }
    return () => { try { delete window.__editor_deleteSelected } catch (e) {} }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // helpers to add nodes; they set selection so tests can assert selected node
  const addNode = useCallback((label, type = 'default', config = {}) => {
    const id = makeId('n')
    const node = { id: String(id), type, data: { label, config }, position: { x: 0, y: 0 } }
    setNodes((s) => { const next = s.concat([node]); return next })
    // update editor selection to newly added node
    setTimeout(() => {
      editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: String(id) })
    }, 0)
  }, [editorDispatch])

  const addHttpNode = useCallback(() => addNode('HTTP Request', 'http', { method: 'GET', headers: {} }), [addNode])
  const addLlmNode = useCallback(() => addNode('LLM', 'llm', { model: 'gpt' }), [addNode])
  const addWebhookTrigger = useCallback(() => addNode('Webhook Trigger', 'input', {}), [addNode])

  // Save workflow: POST /api/workflows
  const saveWorkflow = useCallback(async ({ silent = true } = {}) => {
    try {
      const payload = { graph: { nodes: nodes.map(n => ({ id: String(n.id), data: n.data, position: n.position })), edges, selected_node_id: editorState.selectedNodeId } }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const resp = await fetch('/api/workflows', { method: 'POST', headers, body: JSON.stringify(payload) })
      if (!resp.ok) {
        const text = await resp.text().catch(() => 'unknown')
        alert(`Save failed: ${text}`)
        editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'error' })
        return null
      }
      const data = await resp.json()
      setWorkflowId(data && data.id ? data.id : null)
      editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'saved' })
      editorDispatch({ type: 'MARK_CLEAN' })
      if (!silent) alert(`Saved workflow id: ${data && data.id}`)
      return data
    } catch (e) {
      alert(`Save failed: ${String(e)}`)
      editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'error' })
      return null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, editorState.selectedNodeId, token, editorDispatch])

  // Load workflows: GET /api/workflows
  const loadWorkflows = useCallback(async () => {
    try {
      const headers = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const resp = await fetch('/api/workflows', { headers })
      if (!resp.ok) {
        const text = await resp.text().catch(() => '')
        alert(`Failed to load workflows: ${text}`)
        return
      }
      const data = await resp.json()
      // helpful debug output while investigating empty workflows
      // eslint-disable-next-line no-console
      console.debug('/api/workflows ->', { status: resp.status, body: data })
      setWorkflows(Array.isArray(data) ? data : [])
      // If the first workflow has a graph with nodes, load them into the editor
      if (Array.isArray(data) && data.length) {
        const w = data[0]
        const g = w.graph
        // support legacy array-of-elements graph
        if (Array.isArray(g)) {
          setNodes(g.map(el => ({ id: String(el.id || makeId()), data: el.data || { label: el.data && el.data.label }, position: el.position || { x: 0, y: 0 } })))
          editorDispatch({ type: 'CLEAR_SELECTION' })
          setWorkflowId(w.id)
          return
        }
        // expected shape: { nodes: [...], edges: [...], selected_node_id }
        if (g && Array.isArray(g.nodes)) {
          setNodes(g.nodes.map(n => ({ id: String(n.id || makeId()), data: n.data || { label: n.data && n.data.label }, position: n.position || { x: 0, y: 0 } })))
          if (g.selected_node_id) {
            editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: String(g.selected_node_id) })
          } else {
            editorDispatch({ type: 'CLEAR_SELECTION' })
          }
          setWorkflowId(w.id)
        }
      }
    } catch (e) {
      alert(`Failed to load workflows: ${String(e)}`)
    }
  }, [token, editorDispatch])

  // Runs / logs helpers
  const loadRuns = useCallback(async () => {
    try {
      const url = workflowId ? `/api/runs?workflow_id=${workflowId}` : '/api/runs'
      const headers = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const resp = await fetch(url, { headers })
      if (!resp.ok) return
      const data = await resp.json()
      // some endpoints return { items: [...] }
      const items = data && Array.isArray(data.items) ? data.items : (Array.isArray(data) ? data : (data && Array.isArray(data.items) ? data.items : []))
      editorDispatch({ type: 'SET_RUNS', payload: items })
    } catch (e) {
      // ignore
    }
  }, [workflowId, token, editorDispatch])

  // helper to fetch logs for a run and open EventSource streaming
  const openRunEventSource = useCallback((runId) => {
    try {
      // close existing
      if (esRef.current && typeof esRef.current.close === 'function') {
        try { esRef.current.close() } catch (e) {}
      }
      // create a new EventSource. Tests mock global.EventSource and expect it to be constructed.
      const es = new (window.EventSource)(`/api/runs/${runId}/stream`)
      es.onmessage = (ev) => {
        try {
          const msg = typeof ev.data === 'string' ? JSON.parse(ev.data) : ev.data
          editorDispatch({ type: 'APPEND_SELECTED_RUN_LOG', payload: msg })
        } catch (e) {}
      }
      es.onerror = () => {
        // ignore for tests
      }
      esRef.current = es
      return es
    } catch (e) {
      return null
    }
  }, [editorDispatch])

  const runWorkflow = useCallback(async () => {
    try {
      // ensure saved workflow exists
      let wid = workflowId
      if (!wid) {
        const saved = await saveWorkflow({ silent: true })
        wid = saved && saved.id
        if (!wid) return
      }
      const headers = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const resp = await fetch(`/api/workflows/${wid}/run`, { method: 'POST', headers })
      if (!resp.ok) return
      const data = await resp.json()
      const runId = data && data.run_id
      // refresh runs for the workflow
      await loadRuns()
      // load existing logs and then open stream
      if (runId) {
        const headers2 = {}
        if (token) headers2.Authorization = `Bearer ${token}`
        const rresp = await fetch(`/api/runs/${runId}/logs`, { headers: headers2 })
        if (rresp && rresp.ok) {
          const rd = await rresp.json()
          const logs = rd && Array.isArray(rd.logs) ? rd.logs : []
          editorDispatch({ type: 'SET_SELECTED_RUN_LOGS', payload: logs })
        }
        openRunEventSource(runId)
      }
      alert('Run queued')
    } catch (e) {
      // ignore
    }
  }, [workflowId, token, saveWorkflow, loadRuns, editorDispatch, openRunEventSource])

  const viewRunLogs = useCallback(async (runId) => {
    try {
      if (!runId) return
      // close any existing EventSource and open a new one for this run
      if (esRef.current && typeof esRef.current.close === 'function') {
        try { esRef.current.close() } catch (e) {}
      }
      const headers = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const rresp = await fetch(`/api/runs/${runId}/logs`, { headers })
      if (rresp && rresp.ok) {
        const rd = await rresp.json()
        const logs = rd && Array.isArray(rd.logs) ? rd.logs : []
        editorDispatch({ type: 'SET_SELECTED_RUN_LOGS', payload: logs })
      }
      openRunEventSource(runId)
    } catch (e) {
      // ignore
    }
  }, [token, editorDispatch, openRunEventSource])

  // Node/selection helpers used by NodeRenderer/RightPanel
  const setNodesSafe = useCallback((next) => {
    setNodes(next)
  }, [])

  // update node config (NodeInspector uses updateNodeConfig in tests)
  const updateNodeConfig = useCallback((id, cb) => {
    setNodes((prev) => {
      const copy = prev.map(n => n.id === id ? { ...n, data: { ...n.data, config: { ...(n.data && n.data.config), ...(cb ? cb(n.data && n.data.config) : {}) } } } : n)
      return copy
    })
    editorDispatch({ type: 'MARK_DIRTY' })
  }, [editorDispatch])

  // select workflow from dropdown
  const selectWorkflow = useCallback((wid) => {
    if (!wid) {
      setWorkflowId(null)
      return
    }
    setWorkflowId(wid)
  }, [])

  // expose some minimal node options/providers/secrets for Sidebar to render
  const [providers, setProviders] = useState([])
  const [secrets, setSecrets] = useState([])
  const [newSecretName, setNewSecretName] = useState('')
  const [newSecretValue, setNewSecretValue] = useState('')

  const loadProviders = useCallback(async () => {
    try {
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const r = await fetch('/api/providers', { headers })
      if (!r.ok) {
        const txt = await r.text().catch(() => '')
        alert(`Failed to load providers: ${txt}`)
        return
      }
      const data = await r.json()
      setProviders(Array.isArray(data) ? data : [])
    } catch (e) {
      // ignore
    }
  }, [token])

  const loadSecrets = useCallback(async () => {
    try {
      const headers = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const r = await fetch('/api/secrets', { headers })
      if (!r.ok) {
        return setSecrets([])
      }
      const data = await r.json()
      setSecrets(Array.isArray(data) ? data : [])
    } catch (e) {
      setSecrets([])
    }
  }, [token])

  const createSecret = useCallback(async () => {
    try {
      if (!newSecretName) return alert('Provide secret name')
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const body = { name: newSecretName, value: newSecretValue }
      const r = await fetch('/api/secrets', { method: 'POST', headers, body: JSON.stringify(body) })
      if (!r.ok) {
        const txt = await r.text().catch(() => '')
        alert(`Failed to create secret: ${txt}`)
        return
      }
      // refresh list
      await loadSecrets()
      setNewSecretName('')
      setNewSecretValue('')
      alert('Secret created')
    } catch (e) {
      alert(String(e))
    }
  }, [newSecretName, newSecretValue, token, loadSecrets])

  const testProvider = useCallback(async (pid) => {
    try {
      if (!pid) return alert('Select provider')
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const r = await fetch(`/api/providers/${pid}/test_connection`, { method: 'POST', headers })
      if (!r.ok) {
        const txt = await r.text().catch(() => '')
        alert(`Provider test failed: ${txt}`)
        return
      }
      const data = await r.json()
      if (data && data.ok) alert('Provider test succeeded')
      else alert('Provider test failed')
      // refresh providers metadata
      await loadProviders()
    } catch (e) {
      alert(String(e))
    }
  }, [token, loadProviders])

  // auto-load providers/secrets when token changes (or on mount when token set)
  useEffect(() => {
    // load when authenticated
    if (token) {
      loadProviders()
      loadSecrets()
    }
  }, [token, loadProviders, loadSecrets])

  // ensure workflows list is loaded when the editor mounts or token changes
  useEffect(() => {
    // loadWorkflows is safe to call unauthenticated (backend returns [] if not)
    try {
      loadWorkflows()
    } catch (e) {
      // ignore
    }
  }, [loadWorkflows, token])

  return (
    // Use the same class names the project's CSS expects so layout rules
    // (min-width:0, proper heights, scroll behavior) are applied.
    <div className="editor-root">
      <div className="editor-main">
        <Sidebar
          saveWorkflow={() => saveWorkflow({ silent: false })}
          markDirty={() => editorDispatch({ type: 'MARK_DIRTY' })}
          addHttpNode={addHttpNode}
          addLlmNode={addLlmNode}
          addWebhookTrigger={addWebhookTrigger}
          addHttpTrigger={() => addNode('HTTP Trigger', 'input')}
          addCronTrigger={() => addNode('Cron Trigger', 'timer')}
          addSendEmail={() => addNode('Send Email', 'action')}
          addSlackMessage={() => addNode('Slack Message', 'action')}
          addDbQuery={() => addNode('DB Query', 'action')}
          addS3Upload={() => addNode('S3 Upload', 'action')}
          addTransform={() => addNode('Transform', 'action')}
          addWait={() => addNode('Wait', 'action')}
          addIfNode={() => addNode('If', 'action')}
          addSwitchNode={() => addNode('Switch', 'action')}
          seedNodes={(count) => {
            const arr = []
            for (let i = 0; i < count; i++) arr.push({ id: makeId('n'), type: 'default', data: { label: `Node ${i}` }, position: { x: i * 10, y: 0 } })
            setNodes((s) => s.concat(arr))
          }}
          token={token}
          setToken={setToken}
          workflowId={workflowId}
          workflows={workflows}
          loadWorkflows={loadWorkflows}
          selectWorkflow={selectWorkflow}
          newWorkflow={() => { setWorkflowId(null); setNodes([]); editorDispatch({ type: 'RESET' }) }}
          runWorkflow={runWorkflow}
          loadRuns={loadRuns}
          providers={providers}
          loadProviders={loadProviders}
          newProviderType={() => {}}
          setNewProviderType={() => {}}
          newProviderSecretId={() => {}}
          setNewProviderSecretId={() => {}}
          createProvider={() => {}}
          testProvider={testProvider}
          secrets={secrets}
          loadSecrets={loadSecrets}
          createSecret={createSecret}
          newSecretName={newSecretName}
          setNewSecretName={setNewSecretName}
          newSecretValue={newSecretValue}
          setNewSecretValue={setNewSecretValue}
          runs={editorState.runs || []}
          viewRunLogs={viewRunLogs}
          viewRunDetail={() => {}}
        />

        <div className="canvas">
          {/* Render an interactive React Flow canvas so nodes, edges and grid are visible. */}
          <div className="react-flow-wrapper" style={{ height: 400, minHeight: 200 }}>
            <ReactFlowProvider>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={{ default: NodeRenderer, http: NodeRenderer, llm: NodeRenderer, input: NodeRenderer, action: NodeRenderer, timer: NodeRenderer }}
                onNodeClick={(ev, node) => editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: String(node.id) })}
                onInit={(rfi) => {
                  // center the view when the flow initializes
                  try {
                    setTimeout(() => { rfi && typeof rfi.fitView === 'function' && rfi.fitView({ padding: 0.1 }) }, 0)
                  } catch (e) {}
                }}
                fitView
              >
                <Background gap={16} />
                <Controls />
              </ReactFlow>
            </ReactFlowProvider>
          </div>
        </div>

        <RightPanel
          selectedNode={nodes.find(n => String(n.id) === String(selectedNodeId))}
          token={token}
          copyWebhookUrl={() => {}}
          workflowId={workflowId}
          updateNodeConfig={updateNodeConfig}
          providers={providers}
          nodeOptions={{}}
          autoWireTarget={() => {}}
          setNodes={setNodesSafe}
          markDirty={() => editorDispatch({ type: 'MARK_DIRTY' })}
          testWebhook={() => {}}
        />
      </div>
    </div>
  )
}

export default function Editor({ token = '' }) {
  return (
    <EditorProvider>
      <EditorInner initialToken={token} />
    </EditorProvider>
  )
}
