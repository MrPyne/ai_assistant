import React, { useCallback, useEffect, useRef, useState } from 'react'
import { EditorProvider, useEditorDispatch, useEditorState } from './state/EditorContext'
import Sidebar from './components/Sidebar'
import RightPanel from './components/RightPanel'
import NodeRenderer from './NodeRenderer'
import TemplatesModal from './components/TemplatesModal'
import ReactFlow, { ReactFlowProvider, Background, Controls, applyNodeChanges, applyEdgeChanges, addEdge, MarkerType } from 'react-flow-renderer'

// Keep node types as a stable reference so React Flow doesn't warn or
// reinitialize node renderers on every render. Defining this at module
// scope ensures the object identity is stable.
const NODE_TYPES = { default: NodeRenderer, http: NodeRenderer, llm: NodeRenderer, input: NodeRenderer, action: NodeRenderer, timer: NodeRenderer }

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
  const [edges, setEdges] = useState([])
  const nodesRef = useRef(nodes)
  const selectedNodeId = editorState.selectedNodeId

  // workflow/workflows state used by the Sidebar tests
  const [workflowId, setWorkflowId] = useState(null)
  const [workflows, setWorkflows] = useState([])

  // token used by the Workflows panel (initialize from prop so App can pass auth token)
  const [token, setToken] = useState(initialToken || '')

  // keep local token in sync if the parent passes a new token
  useEffect(() => {
    setToken(initialToken || '')
  }, [initialToken])

  // runs & eventsource handling
  const esRef = useRef(null)
  const runIdRef = useRef(null)

  // keep refs up-to-date for event handlers
  useEffect(() => { nodesRef.current = nodes }, [nodes])

  // expose a simple deleteSelected helper on window for RightPanel to call
  useEffect(() => {
    window.__editor_deleteSelected = () => {
      const sel = editorState.selectedIds || []
      // debug
      // eslint-disable-next-line no-console
      console.debug('__editor_deleteSelected called, sel=', sel)
      if (!sel.length) return
      // remove nodes with ids in sel
      const next = nodesRef.current.filter(n => !sel.includes(String(n.id)))
      setNodes(next)
      // remove edges that reference deleted nodes OR that are individually selected
      setEdges((prev) => prev.filter(e => !sel.includes(String(e.source)) && !sel.includes(String(e.target)) && !sel.includes(String(e.id))))
      editorDispatch({ type: 'CLEAR_SELECTION' })
      editorDispatch({ type: 'MARK_DIRTY' })
    }
    return () => { try { delete window.__editor_deleteSelected } catch (e) {} }
  }, [editorState.selectedIds, editorDispatch])

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
      // include workflow name so updates persist the title
      const payload = { name: editorState.workflowName, graph: { nodes: nodes.map(n => ({ id: String(n.id), data: n.data, position: n.position })), edges: edges.map(e => ({ id: e.id, source: String(e.source), target: String(e.target), source_handle: e.sourceHandle || e.source_handle, target_handle: e.targetHandle || e.target_handle })), selected_node_id: editorState.selectedNodeId } }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      // If we have a workflowId, update via PUT; otherwise create via POST
      const method = workflowId ? 'PUT' : 'POST'
      const url = workflowId ? `/api/workflows/${workflowId}` : '/api/workflows'
      const resp = await fetch(url, { method, headers, body: JSON.stringify(payload) })
      if (!resp.ok) {
        const text = await resp.text().catch(() => 'unknown')
        alert(`Save failed: ${text}`)
        editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'error' })
        return null
      }
      const data = await resp.json()
      // ensure we track the workflow id returned from create/update
      if (data && data.id) setWorkflowId(data.id)
      editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'saved' })
      editorDispatch({ type: 'MARK_CLEAN' })
      // update the stored workflow name after save (PUT/POST may normalize it)
      try { editorDispatch({ type: 'SET_WORKFLOW_NAME', payload: data && data.name ? data.name : editorState.workflowName }) } catch (e) {}
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
      // If the first workflow has a graph with nodes, load them into the editor.
      // Note: the list endpoint may return only metadata (id/name). If so,
      // fetch the single workflow to retrieve its full graph payload.
      if (Array.isArray(data) && data.length) {
        let w = data[0]
        let g = w.graph
        if (!g) {
          // try to fetch the full workflow
          try {
            const r2 = await fetch(`/api/workflows/${w.id}`, { headers })
            if (r2 && r2.ok) {
              const full = await r2.json()
              w = full
              g = full && full.graph
            }
          } catch (e) {
            // ignore \u2014 we'll just not load nodes
          }
        }

        // support legacy array-of-elements graph
        if (Array.isArray(g)) {
          setNodes(g.map(el => ({ id: String(el.id || makeId()), data: el.data || { label: el.data && el.data.label }, position: el.position || { x: 0, y: 0 } })))
          setEdges([])
          editorDispatch({ type: 'CLEAR_SELECTION' })
          setWorkflowId(w.id)
          return
        }
        // expected shape: { nodes: [...], edges: [...], selected_node_id }
        if (g && Array.isArray(g.nodes)) {
          setNodes(g.nodes.map(n => ({ id: String(n.id || makeId()), data: n.data || { label: n.data && n.data.label }, position: n.position || { x: 0, y: 0 } })))
          // map edges into react-flow shape
          if (Array.isArray(g.edges)) {
            setEdges(g.edges.map(e => ({ id: e.id || makeId('e'), source: String(e.source), target: String(e.target), sourceHandle: e.source_handle || e.sourceHandle || null, targetHandle: e.target_handle || e.targetHandle || null })))
          } else {
            setEdges([])
          }
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
  // Note: EventSource (native) cannot send custom headers. When a token
  // is present we prefer to use EventSourcePolyfill which supports headers
  // so the Authorization header can be included like other API calls.
  const openRunEventSource = useCallback(async (runId) => {
    try {
      // close existing
      if (esRef.current && typeof esRef.current.close === 'function') {
        try { esRef.current.close() } catch (e) {}
      }

      // Determine EventSource implementation. Prefer the event-source-polyfill
      // when we have a bearer token so we can send Authorization headers.
      let ESImpl = window.EventSource
      if (token) {
        try {
          const mod = await import('event-source-polyfill')
          ESImpl = mod && (mod.EventSourcePolyfill || mod.default || mod)
        } catch (e) {
          // dynamic import failed; fall back to native EventSource
          ESImpl = window.EventSource
        }
      }

      const es = (ESImpl === window.EventSource)
        ? new ESImpl(`/api/runs/${runId}/stream`)
        : new ESImpl(`/api/runs/${runId}/stream`, { headers: { Authorization: `Bearer ${token}` } })

      // remember which run this EventSource is for so other handlers can
      // inspect it (used to auto-open logs when lifecycle events arrive)
      try { runIdRef.current = runId } catch (e) {}

      // Generic log events (emitted as SSE event 'log')
      es.addEventListener('log', (ev) => {
        try {
          const msg = typeof ev.data === 'string' ? JSON.parse(ev.data) : ev.data
          editorDispatch({ type: 'APPEND_SELECTED_RUN_LOG', payload: msg })
        } catch (e) {}
      })

      // Node-level structured events (emitted as SSE event 'node')
      es.addEventListener('node', (ev) => {
        try {
          const payload = typeof ev.data === 'string' ? JSON.parse(ev.data) : ev.data
          // append to run logs view so users still see structured node events
          editorDispatch({ type: 'APPEND_SELECTED_RUN_LOG', payload })
          // Auto-open the right panel and switch to the Runs tab when this
          // run emits lifecycle events (started/completed) so users see
          // live updates without clicking "View logs".
          try {
            // payload.run_id may be number or string depending on source
            const currentRun = runIdRef.current
            if (payload && currentRun && String(payload.run_id) === String(currentRun) && (payload.status === 'started' || payload.status === 'success' || payload.status === 'failed')) {
              editorDispatch({ type: 'SET_RIGHT_PANEL_OPEN', payload: true })
              editorDispatch({ type: 'SET_ACTIVE_RIGHT_TAB', payload: 'runs' })
            }
          } catch (e) {}
          // update node visual state in the editor canvas
          try {
            const nid = payload && payload.node_id ? String(payload.node_id) : null
            if (nid) {
              setNodes((prev) => {
                return prev.map((n) => {
                  if (String(n.id) !== String(nid)) return n
                  // attach runtime info under data.runtime so existing tests
                  // that inspect node.data.config are unaffected.
                  const existingData = n.data || {}
                  return { ...n, data: { ...existingData, runtime: payload } }
                })
              })
            }
          } catch (e) {
            // ignore node update errors
          }
        } catch (e) {}
      })

      // Terminal status events (emitted as SSE event 'status')
      es.addEventListener('status', (ev) => {
        try {
          const payload = typeof ev.data === 'string' ? JSON.parse(ev.data) : ev.data
          editorDispatch({ type: 'APPEND_SELECTED_RUN_LOG', payload })
          // refresh runs list so run state in left panel updates
          try { loadRuns() } catch (e) {}
        } catch (e) {}
        try { es.close() } catch (e) {}
      })

      es.onerror = () => {
        // ignore for tests; real UI might show reconnect/backoff here
      }
      esRef.current = es
      // attach a cleanup hook so when the EventSource is closed we clear the
      // runIdRef to avoid stale associations
      const origClose = es.close && es.close.bind(es)
      es.close = () => {
        try { runIdRef.current = null } catch (e) {}
        try { if (origClose) origClose() } catch (e) {}
      }
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
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      // send an explicit JSON body (empty object) so FastAPI receives a valid
      // application/json payload. Some endpoints expect a JSON body and will
      // return 422 if none is provided.
      const resp = await fetch(`/api/workflows/${wid}/run`, { method: 'POST', headers, body: JSON.stringify({}) })
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
      const copy = prev.map(n => {
        if (n.id !== id) return n
        const existing = (n.data && n.data.config) || {}
        let delta = {}
        try {
          if (typeof cb === 'function') {
            delta = cb(existing) || {}
          } else if (cb && typeof cb === 'object') {
            delta = cb
          } else {
            delta = {}
          }
        } catch (e) {
          delta = {}
        }
        return { ...n, data: { ...n.data, config: { ...existing, ...delta } } }
      })
      return copy
    })
    editorDispatch({ type: 'MARK_DIRTY' })
  }, [editorDispatch])

  // react-flow change handlers so nodes/edges are interactive
  const onNodesChange = useCallback((changes) => {
    setNodes((nds) => applyNodeChanges(changes, nds))
    editorDispatch({ type: 'MARK_DIRTY' })
  }, [editorDispatch])

  const onEdgesChange = useCallback((changes) => {
    setEdges((eds) => applyEdgeChanges(changes, eds))
    editorDispatch({ type: 'MARK_DIRTY' })
  }, [editorDispatch])

  // keep React Flow selection in sync with our EditorContext selection model
  const onSelectionChange = useCallback((sel) => {
    try {
      // sel may be an object { nodes: [...], edges: [...] } or an array depending on RF version
      let ids = []
      if (Array.isArray(sel)) ids = sel.map(i => String(i))
      else if (sel && typeof sel === 'object') {
        if (Array.isArray(sel.nodes)) ids = ids.concat(sel.nodes.map(n => String(n.id)))
        if (Array.isArray(sel.edges)) ids = ids.concat(sel.edges.map(e => String(e.id)))
      }
      // dispatch SET_SELECTION with the list of ids
      editorDispatch({ type: 'SET_SELECTION', payload: ids })
    } catch (e) {
      // swallow selection sync errors
    }
  }, [editorDispatch])

  const onConnect = useCallback((connection) => {
    setEdges((eds) => addEdge(connection, eds))
    editorDispatch({ type: 'MARK_DIRTY' })
  }, [editorDispatch])

  // select workflow from dropdown
  const selectWorkflow = useCallback((wid) => {
    if (!wid) {
      setWorkflowId(null)
      // clear editor when selecting "New workflow"
      setNodes([])
      setEdges([])
      editorDispatch({ type: 'RESET' })
      return
    }
    // when choosing an existing workflow from the dropdown we should fetch
    // and apply its full graph to the editor so Save will update that id.
    ;(async () => {
      try {
        const headers = {}
        if (token) headers.Authorization = `Bearer ${token}`
        const r = await fetch(`/api/workflows/${wid}`, { headers })
        if (!r.ok) {
          // still set id so user can create separate workflow or retry
          setWorkflowId(wid)
          return
        }
        const w = await r.json()
        const g = w && w.graph
        if (Array.isArray(g)) {
          setNodes(g.map(el => ({ id: String(el.id || makeId()), data: el.data || { label: el.data && el.data.label }, position: el.position || { x: 0, y: 0 } })))
          setEdges([])
        } else if (g && Array.isArray(g.nodes)) {
          setNodes(g.nodes.map(n => ({ id: String(n.id || makeId()), data: n.data || { label: n.data && n.data.label }, position: n.position || { x: 0, y: 0 } })))
          if (Array.isArray(g.edges)) {
            setEdges(g.edges.map(e => ({ id: e.id || makeId('e'), source: String(e.source), target: String(e.target), sourceHandle: e.source_handle || e.sourceHandle || null, targetHandle: e.target_handle || e.targetHandle || null })))
          } else {
            setEdges([])
          }
          if (g.selected_node_id) {
            editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: String(g.selected_node_id) })
          } else {
            editorDispatch({ type: 'CLEAR_SELECTION' })
          }
        }
        setWorkflowId(wid)
        // update workflow name in editor state
        try { editorDispatch({ type: 'SET_WORKFLOW_NAME', payload: w && w.name ? w.name : editorState.workflowName }) } catch (e) {}
      } catch (e) {
        setWorkflowId(wid)
      }
    })()
  }, [editorDispatch, token, editorState.workflowName])

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

  // ensure runs list is loaded whenever the selected workflow changes (or
  // when the editor first mounts and loadWorkflows set a workflowId). This
  // populates the Runs dropdown in the left panel on first load so users
  // don't have to manually click "Refresh Runs".
  useEffect(() => {
    try {
      // loadRuns is safe to call even when workflowId is null (it will list
      // all runs). Prefer calling the memoized callback directly so tests
      // and callers observe the same behavior.
      loadRuns()
    } catch (e) {
      // ignore
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadRuns])

  // react-flow instance ref so we can call fitView after nodes/edges are loaded
  const rfInstanceRef = useRef(null)

  // nodeOptions helper: NodeInspector expects a function that returns
  // selectable node targets for wiring. Provide a stable callback that
  // excludes the currently-selected node (so you can't wire a node to
  // itself) and returns { id, label } objects.
  const nodeOptions = useCallback((excludeId) => {
    try {
      return nodes
        .filter(n => String(n.id) !== String(excludeId))
        .map(n => ({ id: String(n.id), label: (n.data && n.data.label) || String(n.id) }))
    } catch (e) {
      return []
    }
  }, [nodes])

  // whenever nodes or edges change, center/fit the view so the graph is visible.
  // Support React Flow variations that expose onInit or onLoad by capturing
  // the instance in either callback below.
  useEffect(() => {
    try {
      if (!rfInstanceRef.current || typeof rfInstanceRef.current.fitView !== 'function') return
      // give the DOM a moment to settle so fitView computes correctly
      const t = setTimeout(() => {
        try {
          rfInstanceRef.current.fitView({ padding: 0.12 })
        } catch (e) {
          // swallow transient errors
        }
      }, 50)
      return () => clearTimeout(t)
    } catch (e) {
      // ignore
    }
  }, [nodes.length, edges.length])

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
          newWorkflow={() => { setWorkflowId(null); setNodes([]); setEdges([]); editorDispatch({ type: 'RESET' }) }}
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

        {/* Templates modal: uses EditorContext.showTemplates to control visibility */}
        <TemplatesModal
          open={!!editorState.showTemplates}
          token={token}
          onClose={() => editorDispatch({ type: 'SET_SHOW_TEMPLATES', payload: false })}
          onApply={(graph) => {
            try {
              // Support legacy array-of-elements or { nodes, edges }
              let g = graph
              if (Array.isArray(graph)) {
                g = { nodes: graph, edges: [] }
              }
              if (!g) return
              const nextNodes = Array.isArray(g.nodes) ? g.nodes.map(n => ({ id: String(n.id || makeId()), type: n.type === 'input' ? 'input' : (n.type || 'default'), position: n.position || { x: 0, y: 0 }, data: n.data || { label: n.data && n.data.label } })) : []
              const nextEdges = Array.isArray(g.edges) ? g.edges.map(e => ({ id: e.id || makeId('e'), source: String(e.source), target: String(e.target), sourceHandle: e.source_handle || e.sourceHandle || null, targetHandle: e.target_handle || e.targetHandle || null })) : []
              setNodes(nextNodes)
              setEdges(nextEdges)
              editorDispatch({ type: 'SET_SHOW_TEMPLATES', payload: false })
            } catch (e) {
              // ignore
            }
          }}
        />

        <div className="canvas">
          {/* Render an interactive React Flow canvas so nodes, edges and grid are visible. */}
          {/* Use 100% height so it fills the canvas card; minHeight keeps it usable on small screens */}
          <div className="reactflow-wrapper" style={{ height: '100%', minHeight: 600 }}>
            <ReactFlowProvider>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={NODE_TYPES}
                onNodeClick={(ev, node) => editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: String(node.id) })}
                onSelectionChange={onSelectionChange}
                onInit={(rfi) => { try { rfInstanceRef.current = rfi } catch (e) {} }}
                // some React Flow versions call onLoad instead of onInit
                onLoad={(rfi) => { try { rfInstanceRef.current = rfi } catch (e) {} }}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                // enable common interactions and sane zoom limits
                zoomOnScroll={true}
                zoomOnPinch={true}
                panOnScroll={true}
                panOnDrag={true}
                minZoom={0.05}
                maxZoom={2}
                fitView={false}
                fitViewOptions={{ padding: 0.12 }}
                // show an arrow head at the end of each edge for better
                // directionality. MarkerType is provided by react-flow v10.
                defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}
                style={{ width: '100%', height: '100%' }}
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
          nodeOptions={nodeOptions}
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
