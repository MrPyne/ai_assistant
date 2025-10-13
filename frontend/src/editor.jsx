import React, { useRef, useEffect, useState, useCallback } from 'react'
import ReactFlow, { ReactFlowProvider, Background, Controls, applyNodeChanges, applyEdgeChanges, addEdge } from 'react-flow-renderer'
import 'react-flow-renderer/dist/style.css'
import Sidebar from './components/Sidebar'
import RightPanel from './components/RightPanel'
import NodeRenderer from './NodeRenderer'
import TemplatePreview from './components/TemplatePreview'
import { useEditorDispatch, useEditorState } from './state/EditorContext'

const NODE_TYPES = { default: NodeRenderer, input: NodeRenderer }

export default function Editor({ token }) {
  const logEventSourceRef = useRef(null)
  const editorDispatch = useEditorDispatch()
  const editorState = useEditorState()

  // local nodes/edges state for the canvas
  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const [workflows, setWorkflows] = useState([])
  const [providersList, setProviders] = useState([])
  const [secretsList, setSecrets] = useState([])
  const [runsList, setRuns] = useState([])
  const nextIdRef = useRef(1)
  const [tokenState, setToken] = useState(token || '')

  // keep EventSource behavior but use EditorContext dispatch directly
  const viewRunLogs = useCallback(async (runId) => {
    try {
      const url = token ? `/api/runs/${runId}/stream?access_token=${token}` : `/api/runs/${runId}/stream`
      const es = new EventSource(url)
      es.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data)
          editorDispatch({ type: 'APPEND_SELECTED_RUN_LOG', payload })
        } catch (err) {}
      }
      es.onerror = (err) => {
        try { es.close() } catch (e) {}
        logEventSourceRef.current = null
      }
      logEventSourceRef.current = es
    } catch (err) {}
  }, [editorDispatch, token])

  // expose viewRunLogs globally for callers that previously invoked editor.viewRunLogs
  useEffect(() => {
    window.__editor_viewRunLogs = viewRunLogs
    return () => { delete window.__editor_viewRunLogs }
  }, [viewRunLogs])

  // basic node operations used by Sidebar / Inspector
  const addNode = useCallback((label, type = 'default', initialConfig = {}) => {
    const id = String(nextIdRef.current++)
    const newNode = {
      id,
      type: type === 'input' ? 'input' : 'default',
      position: { x: 50 + (nodes.length * 40), y: 50 + (nodes.length * 20) },
      data: { label, config: initialConfig },
    }
    setNodes((nds) => [...nds, newNode])
    // select the new node
    editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: id })
    return id
  }, [editorDispatch, nodes.length])

  const addHttpNode = useCallback(() => addNode('HTTP Request', 'default', { method: 'GET', url: '' }), [addNode])
  const addLlmNode = useCallback(() => addNode('LLM', 'default', { prompt: '' }), [addNode])
  const addWebhookTrigger = useCallback(() => addNode('Webhook Trigger', 'input', {}), [addNode])
  const addHttpTrigger = useCallback(() => addNode('HTTP Trigger', 'input', { capture_headers: true }), [addNode])
  const addCronTrigger = useCallback(() => addNode('Cron Trigger', 'input', { cron: '0 * * * *', timezone: 'UTC', enabled: true }), [addNode])
  const addSendEmail = useCallback(() => addNode('Send Email', 'default', { to: 'user@example.com', from: '', subject: '', body: '', provider_id: null }), [addNode])
  const addSlackMessage = useCallback(() => addNode('Slack Message', 'default', { channel: '#alerts', text: '', provider_id: null }), [addNode])
  const addDbQuery = useCallback(() => addNode('DB Query', 'default', { provider_id: null, query: 'SELECT 1' }), [addNode])
  const addS3Upload = useCallback(() => addNode('S3 Upload', 'default', { bucket: '', key: '', body_template: '{{input}}', provider_id: null }), [addNode])
  const addTransform = useCallback(() => addNode('Transform', 'default', { language: 'jinja', template: '{{ input }}', input_path: '' }), [addNode])
  const addWait = useCallback(() => addNode('Wait', 'default', { seconds: 60 }), [addNode])
  const addIfNode = useCallback(() => addNode('If'), [addNode])
  const addSwitchNode = useCallback(() => addNode('Switch'), [addNode])

  const updateNodeConfig = useCallback((nodeId, newConfig) => {
    setNodes((nds) => nds.map(n => n.id === String(nodeId) ? { ...n, data: { ...(n.data || {}), config: newConfig } } : n))
  }, [])

  const nodeOptions = useCallback((forId) => {
    return nodes.map(n => ({ id: n.id, label: (n.data && n.data.label) || n.id }))
  }, [nodes])

  const autoWireTarget = useCallback((nodeId, targetId) => {
    if (!nodeId || !targetId) return
    const edge = { id: `${nodeId}-${targetId}`, source: String(nodeId), target: String(targetId) }
    setEdges((es) => [...es, edge])
  }, [])

  const markDirty = useCallback(() => editorDispatch({ type: 'MARK_DIRTY' }), [editorDispatch])

  const copyWebhookUrl = useCallback(() => {
    const sel = editorState.selectedNodeId
    const wf = window.location.origin + `/api/webhook/${/*workflowId*/ ''}/${sel}`
    try { navigator.clipboard && navigator.clipboard.writeText(wf); alert('Copied webhook URL') } catch (e) { alert(wf) }
  }, [editorState.selectedNodeId])

  const saveWorkflow = useCallback(async ({ silent } = { silent: false }) => {
    editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'saving' })
    try {
      const body = { name: editorState.workflowName, graph: { nodes: nodes.map(n => ({ id: n.id, type: n.type, position: n.position, data: n.data })), edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target })) } }
      const headers = { 'Content-Type': 'application/json' }
      if (tokenState) headers.Authorization = `Bearer ${tokenState}`
      let res
      // naive: if there is a selected workflow id, try to PUT otherwise POST
      const wfId = null
      if (wfId) {
        res = await fetch(`/api/workflows/${wfId}`, { method: 'PUT', headers, body: JSON.stringify(body) })
      } else {
        res = await fetch('/api/workflows', { method: 'POST', headers, body: JSON.stringify(body) })
      }
      if (!res.ok) throw new Error('Save failed')
      editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'saved' })
      editorDispatch({ type: 'SET_LAST_SAVED_AT', payload: Date.now() })
      if (!silent) alert('Workflow saved')
      return await res.json()
    } catch (e) {
      editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'error' })
      if (!silent) alert('Save failed')
      return null
    }
  }, [editorDispatch, editorState.workflowName, nodes, edges, tokenState])

  const loadWorkflows = useCallback(async () => {
    try {
      const headers = {}
      if (tokenState) headers.Authorization = `Bearer ${tokenState}`
      const r = await fetch('/api/workflows', { headers })
      if (!r.ok) return setWorkflows([])
      const data = await r.json()
      setWorkflows(Array.isArray(data) ? data : [])
    } catch (e) { setWorkflows([]) }
  }, [tokenState])

  const testProvider = useCallback(async (providerId, inlineSecret = null) => {
    try {
      const headers = { 'Content-Type': 'application/json' }
      if (tokenState) headers.Authorization = `Bearer ${tokenState}`
      const body = inlineSecret ? { secret: inlineSecret } : {}
      const r = await fetch(`/api/providers/${providerId}/test_connection`, { method: 'POST', headers, body: JSON.stringify(body) })
      if (!r.ok) {
        const txt = await r.text()
        alert('Test failed: ' + txt)
        return false
      }
      const data = await r.json()
      if (data && data.ok) {
        alert('Test succeeded')
        return true
      }
      alert('Test failed')
      return false
    } catch (e) { alert('Test failed: ' + String(e)); return false }
  }, [tokenState])

  const selectWorkflow = useCallback(async (wfId) => {
    if (!wfId) return
    try {
      const headers = {}
      if (tokenState) headers.Authorization = `Bearer ${tokenState}`
      const r = await fetch(`/api/workflows/${wfId}`, { headers })
      if (!r.ok) return
      const data = await r.json()
      const graph = data.graph || data
      const newNodes = (graph.nodes || []).map(n => ({ id: String(n.id), type: n.type === 'input' ? 'input' : 'default', position: n.position || { x: 0, y: 0 }, data: { label: n.data && n.data.label ? n.data.label : 'Node', config: n.data && n.data.config ? n.data.config : {} } }))
      const newEdges = (graph.edges || []).map(e => ({ id: e.id ? String(e.id) : `${e.source}-${e.target}`, source: String(e.source), target: String(e.target) }))
      setNodes(newNodes)
      setEdges(newEdges)
    } catch (e) {}
  }, [tokenState])

  const newWorkflow = useCallback(() => {
    setNodes([])
    setEdges([])
    editorDispatch({ type: 'RESET', payload: { workflowName: 'New Workflow' } })
  }, [editorDispatch])

  const runWorkflow = useCallback(async (wfId) => {
    if (!wfId) return alert('No workflow selected')
    try {
      const headers = { 'Content-Type': 'application/json' }
      if (tokenState) headers.Authorization = `Bearer ${tokenState}`
      const r = await fetch(`/api/workflows/${wfId}/run`, { method: 'POST', headers })
      if (!r.ok) throw new Error('Run failed')
      alert('Run started')
    } catch (e) { alert('Run failed') }
  }, [tokenState])

  const loadRuns = useCallback(async () => {
    try {
      const headers = {}
      if (tokenState) headers.Authorization = `Bearer ${tokenState}`
      const r = await fetch('/api/runs', { headers })
      if (!r.ok) return setRuns([])
      const data = await r.json()
      setRuns(Array.isArray(data) ? data : [])
      editorDispatch({ type: 'SET_RUNS', payload: Array.isArray(data) ? data : [] })
    } catch (e) { setRuns([]) }
  }, [tokenState, editorDispatch])

  const loadProviders = useCallback(async () => {
    try {
      const headers = {}
      if (tokenState) headers.Authorization = `Bearer ${tokenState}`
      const r = await fetch('/api/providers', { headers })
      if (!r.ok) return setProviders([])
      const data = await r.json()
      setProviders(Array.isArray(data) ? data : [])
    } catch (e) { setProviders([]) }
  }, [tokenState])

  const loadSecrets = useCallback(async () => {
    try {
      const headers = {}
      if (tokenState) headers.Authorization = `Bearer ${tokenState}`
      const r = await fetch('/api/secrets', { headers })
      if (!r.ok) return setSecrets([])
      const data = await r.json()
      setSecrets(Array.isArray(data) ? data : [])
    } catch (e) { setSecrets([]) }
  }, [tokenState])
  const viewRunDetail = useCallback((runId) => { editorDispatch({ type: 'SET_SELECTED_RUN_DETAIL', payload: { id: runId } }) }, [editorDispatch])
  const providers = providersList
  const secrets = secretsList
  // workflows variable is now managed via state
  // runs is mirrored into editor state by loadRuns
  const runs = editorState.runs || runsList

  const onNodeClick = useCallback((event, node) => {
    if (node && node.id) editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: String(node.id) })
  }, [editorDispatch])

  // derive selectedNode object to pass into inspector
  const selectedNode = nodes.find(n => String(n.id) === String(editorState.selectedNodeId)) || null

  // Built-in templates for the Browse templates modal
  const TEMPLATES = [
    {
      id: 'http-llm',
      name: 'HTTP - LLM',
      description: 'Fetch data via HTTP then process with an LLM node',
      graph: {
        nodes: [
          { id: '1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Webhook Trigger', config: {} } },
          { id: '2', type: 'default', position: { x: 240, y: 0 }, data: { label: 'HTTP Request', config: { method: 'GET', url: 'https://api.example.com/data' } } },
          { id: '3', type: 'default', position: { x: 480, y: 0 }, data: { label: 'LLM', config: { prompt: 'Summarize: {{input}}' } } },
        ],
        edges: [
          { id: '1-2', source: '1', target: '2' },
          { id: '2-3', source: '2', target: '3' },
        ],
      },
    },
    {
      id: 'simple-webhook',
      name: 'Webhook - HTTP',
      description: 'Simple webhook that forwards payload to an HTTP request',
      graph: {
        nodes: [
          { id: '1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Webhook Trigger', config: {} } },
          { id: '2', type: 'default', position: { x: 240, y: 0 }, data: { label: 'HTTP Request', config: { method: 'POST', url: 'https://webhook.example/ingest' } } },
        ],
        edges: [ { id: '1-2', source: '1', target: '2' } ],
      },
    },
  ]

  const applyTemplate = useCallback((tpl) => {
    const graph = tpl.graph || { nodes: [], edges: [] }
    const newNodes = (graph.nodes || []).map(n => ({ id: String(n.id), type: n.type === 'input' ? 'input' : 'default', position: n.position || { x: 0, y: 0 }, data: { label: n.data && n.data.label ? n.data.label : 'Node', config: n.data && n.data.config ? n.data.config : {} } }))
    const newEdges = (graph.edges || []).map(e => ({ id: e.id ? String(e.id) : `${e.source}-${e.target}`, source: String(e.source), target: String(e.target) }))
    setNodes(newNodes)
    setEdges(newEdges)
    editorDispatch({ type: 'SET_SHOW_TEMPLATES', payload: false })
    editorDispatch({ type: 'SET_WORKFLOW_NAME', payload: tpl.name || 'Template' })
    editorDispatch({ type: 'MARK_DIRTY' })
  }, [editorDispatch])

  // helper to seed N demo nodes onto the canvas
  const seedNodes = useCallback((count = 10) => {
    const created = []
    setNodes((nds) => {
      const startIndex = nds.length
      const next = [...nds]
      for (let i = 0; i < count; i++) {
        const id = String(nextIdRef.current++)
        const label = `Demo ${startIndex + i + 1}`
        const node = { id, type: 'default', position: { x: 50 + ((startIndex + i) * 40), y: 50 + ((startIndex + i) * 20) }, data: { label, config: {} } }
        next.push(node)
        created.push(node)
      }
      return next
    })
    // optionally focus/select the last created node
    if (created.length) {
      const last = created[created.length - 1]
      editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: last.id })
    }
    editorDispatch({ type: 'MARK_DIRTY' })
  }, [editorDispatch])

  // Auto-load lists when token changes (or on mount if token is set)
  useEffect(() => {
    if (tokenState) {
      loadWorkflows()
      loadRuns()
      loadProviders()
      loadSecrets()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tokenState])

  return (
    // let the CSS rules control the editor height (keeps it in sync with the topbar)
    <div className="editor-root" style={{ display: 'flex' }}>
      <div className="editor-main" style={{ display: 'flex', height: '100%', alignItems: 'stretch' }}>
        <Sidebar
        saveWorkflow={saveWorkflow}
        markDirty={markDirty}
        addHttpNode={addHttpNode}
        addLlmNode={addLlmNode}
        addWebhookTrigger={addWebhookTrigger}
        addHttpTrigger={addHttpTrigger}
        addCronTrigger={addCronTrigger}
        addSendEmail={addSendEmail}
        addSlackMessage={addSlackMessage}
        addDbQuery={addDbQuery}
        addS3Upload={addS3Upload}
        addTransform={addTransform}
        addWait={addWait}
        addIfNode={addIfNode}
        addSwitchNode={addSwitchNode}
        token={tokenState}
        setToken={setToken}
        workflowId={null}
        workflows={workflows}
        loadWorkflows={loadWorkflows}
        selectWorkflow={selectWorkflow}
        newWorkflow={newWorkflow}
        runWorkflow={runWorkflow}
        loadRuns={loadRuns}
        providers={providers}
        newProviderType={''}
        setNewProviderType={() => {}}
        newProviderSecretId={''}
        setNewProviderSecretId={() => {}}
        createProvider={() => {}}
        testProvider={testProvider}
        secrets={secrets}
        loadSecrets={loadSecrets}
        createSecret={() => {}}
        newSecretName={''}
        setNewSecretName={() => {}}
        newSecretValue={''}
        setNewSecretValue={() => {}}
        runs={runs}
        viewRunLogs={viewRunLogs}
        viewRunDetail={viewRunDetail}
      />

        <div className="canvas" style={{ flex: 1 }}>
          <ReactFlowProvider>
          {/* match existing CSS selectors by including the reactflow-wrapper */}
          <div className="reactflow-wrapper" style={{ height: '100%' }}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              onNodeClick={onNodeClick}
              onNodesChange={(changes) => setNodes((nds) => applyNodeChanges(changes, nds))}
              onEdgesChange={(changes) => setEdges((eds) => applyEdgeChanges(changes, eds))}
              onConnect={(conn) => setEdges((eds) => addEdge(conn, eds))}
              nodesDraggable={true}
              nodesConnectable={true}
              fitView
              style={{ width: '100%', height: '100%' }}
            >
              <Background />
              <Controls />
            </ReactFlow>
          </div>
          </ReactFlowProvider>
        </div>
      </div>

      {editorState.showTemplates ? (
        <div className="templates-overlay">
          <div className="templates-modal">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0 }}>Templates</h3>
              <button onClick={() => editorDispatch({ type: 'SET_SHOW_TEMPLATES', payload: false })}>Close</button>
            </div>
            <div className="templates-list">
              {TEMPLATES.map((tpl) => (
                <div key={tpl.id} className="template-card">
                  <h4 style={{ marginTop: 6 }}>{tpl.name}</h4>
                  <div className="muted" style={{ marginBottom: 8 }}>{tpl.description}</div>
                  <TemplatePreview graph={tpl.graph} height={120} />
                  <div className="template-actions">
                    <button onClick={() => applyTemplate(tpl)}>Use template</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      <RightPanel
        selectedNode={selectedNode}
        token={tokenState}
        copyWebhookUrl={copyWebhookUrl}
        workflowId={null}
        updateNodeConfig={updateNodeConfig}
        providers={providers}
        nodeOptions={nodeOptions}
        autoWireTarget={autoWireTarget}
        setNodes={setNodes}
        markDirty={markDirty}
        testWebhook={() => { alert('Test webhook (stub)') }}
      />
    </div>
  )
}
