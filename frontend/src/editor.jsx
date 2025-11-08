import React, { useCallback, useEffect, useRef, useState } from 'react'
import useRuns from './hooks/useRuns'
import useNodes from './hooks/useNodes'
import { EditorProvider, useEditorDispatch, useEditorState } from './state/EditorContext'
import Sidebar from './components/Sidebar'
import RightPanel from './components/RightPanel'
import NodeRenderer from './NodeRenderer'
import TemplatesModal from './components/TemplatesModal'
import ReactFlow, { ReactFlowProvider, Background, Controls, applyNodeChanges, applyEdgeChanges, addEdge, MarkerType } from 'react-flow-renderer'

const NODE_TYPES = { default: NodeRenderer, http: NodeRenderer, llm: NodeRenderer, input: NodeRenderer, action: NodeRenderer, timer: NodeRenderer }

function makeId(prefix = 'n') {
  return `${prefix}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1000)}`
}

function EditorInner({ initialToken = '' }) {
  const editorDispatch = useEditorDispatch()
  const editorState = useEditorState()

  const { nodes, edges, setNodes, setEdges, nodesRef, setNodesSafe, addNode, onNodesChange, onEdgesChange, onConnect, updateNodeConfig, nodeOptions, deleteSelected } = useNodes({ editorDispatch })
  const selectedNodeId = editorState.selectedNodeId

  const [workflowId, setWorkflowId] = useState(null)
  const [workflows, setWorkflows] = useState([])

  const [token, setToken] = useState(initialToken || '')
  useEffect(() => { setToken(initialToken || '') }, [initialToken])

  useEffect(() => { nodesRef.current = nodes }, [nodes])

  useEffect(() => {
    window.__editor_deleteSelected = () => {
      try { deleteSelected(editorState.selectedIds || [], editorDispatch) } catch (e) {}
    }
    return () => { try { delete window.__editor_deleteSelected } catch (e) {} }
  }, [editorState.selectedIds, editorDispatch, deleteSelected])

  const addHttpNode = useCallback(() => addNode('HTTP Request', 'http', { method: 'GET', headers: {} }), [addNode])
  const addLlmNode = useCallback(() => addNode('LLM', 'llm', { model: 'gpt' }), [addNode])
  const addWebhookTrigger = useCallback(() => addNode('Webhook Trigger', 'input', {}), [addNode])

  const saveWorkflow = useCallback(async ({ silent = true } = {}) => {
    try {
      const payload = { name: editorState.workflowName, graph: { nodes: nodes.map(n => ({ id: String(n.id), data: n.data, position: n.position })), edges: edges.map(e => ({ id: e.id, source: String(e.source), target: String(e.target), source_handle: e.sourceHandle || e.source_handle, target_handle: e.targetHandle || e.target_handle })), selected_node_id: editorState.selectedNodeId } }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
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
      if (data && data.id) setWorkflowId(data.id)
      try {
        if (data && data.validation_warnings && Array.isArray(data.validation_warnings) && data.validation_warnings.length) {
          editorDispatch({ type: 'SET_VALIDATION_ERROR', payload: data.validation_warnings })
        } else {
          editorDispatch({ type: 'SET_VALIDATION_ERROR', payload: null })
        }
      } catch (e) {}
      editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'saved' })
      editorDispatch({ type: 'MARK_CLEAN' })
      try { editorDispatch({ type: 'SET_WORKFLOW_NAME', payload: data && data.name ? data.name : editorState.workflowName }) } catch (e) {}
      if (!silent) alert(`Saved workflow id: ${data && data.id}`)
      return data
    } catch (e) {
      try { editorDispatch({ type: 'SET_VALIDATION_ERROR', payload: null }) } catch (er) {}
      alert(`Save failed: ${String(e)}`)
      editorDispatch({ type: 'SET_SAVE_STATUS', payload: 'error' })
      return null
    }
  }, [nodes, edges, editorState.selectedNodeId, token, editorDispatch])

  const { loadRuns, openRunEventSource, runWorkflow, viewRunLogs } = useRuns({ workflowId, token, setNodes, editorDispatch, saveWorkflow })

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
      console.debug('/api/workflows ->', { status: resp.status, body: data })
      setWorkflows(Array.isArray(data) ? data : [])
      if (Array.isArray(data) && data.length) {
        let w = data[0]
        let g = w.graph
        if (!g) {
          try {
            const r2 = await fetch(`/api/workflows/${w.id}`, { headers })
            if (r2 && r2.ok) {
              const full = await r2.json()
              w = full
              g = full && full.graph
            }
          } catch (e) {}
        }

        if (Array.isArray(g)) {
          setNodes(g.map(el => ({ id: String(el.id || makeId()), data: el.data || { label: el.data && el.data.label }, position: el.position || { x: 0, y: 0 } })))
          setEdges([])
          editorDispatch({ type: 'CLEAR_SELECTION' })
          setWorkflowId(w.id)
          return
        }
        if (g && Array.isArray(g.nodes)) {
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
          setWorkflowId(w.id)
        }
      }
    } catch (e) {
      alert(`Failed to load workflows: ${String(e)}`)
    }
  }, [token, editorDispatch])

  // Attempt to load providers/secrets whenever token changes (including on mount).
  // The backend will return 401 when no auth is present; loadProviders now handles that
  // case gracefully so we avoid noisy alerts when unauthenticated.
  useEffect(() => { try { loadProviders(); loadSecrets() } catch (e) {} }, [token])

  useEffect(() => { try { loadWorkflows() } catch (e) {} }, [loadWorkflows, token])

  useEffect(() => { try { loadRuns() } catch (e) {} }, [loadRuns])

  const onSelectionChange = useCallback((sel) => {
    try {
      let ids = []
      if (Array.isArray(sel)) ids = sel.map(i => String(i))
      else if (sel && typeof sel === 'object') {
        if (Array.isArray(sel.nodes)) ids = ids.concat(sel.nodes.map(n => String(n.id)))
        if (Array.isArray(sel.edges)) ids = ids.concat(sel.edges.map(e => String(e.id)))
      }
      editorDispatch({ type: 'SET_SELECTION', payload: ids })
    } catch (e) {}
  }, [editorDispatch])

  const selectWorkflow = useCallback((wid) => {
    if (!wid) {
      setWorkflowId(null)
      setNodes([])
      setEdges([])
      editorDispatch({ type: 'RESET' })
      return
    }
    ;(async () => {
      try {
        const headers = {}
        if (token) headers.Authorization = `Bearer ${token}`
        const r = await fetch(`/api/workflows/${wid}`, { headers })
        if (!r.ok) {
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
        try { editorDispatch({ type: 'SET_WORKFLOW_NAME', payload: w && w.name ? w.name : editorState.workflowName }) } catch (e) {}
      } catch (e) {
        setWorkflowId(wid)
      }
    })()
  }, [editorDispatch, token, editorState.workflowName])

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
        // If unauthenticated simply treat as no providers rather than noisy alert.
        if (r.status === 401) {
          console.debug('loadProviders: unauthenticated (401), not loading providers')
          setProviders([])
          return
        }
        alert(`Failed to load providers: ${txt}`)
        return
      }
      const data = await r.json()
      setProviders(Array.isArray(data) ? data : [])
    } catch (e) {}
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
      await loadProviders()
    } catch (e) {
      alert(String(e))
    }
  }, [token, loadProviders])

  useEffect(() => {
    window.__editor_runWorkflow = async () => {
      try {
        const saved = await saveWorkflow({ silent: true })
        const wid = saved && saved.id
        if (!wid) return
        try { await runWorkflow() } catch (e) {}
      } catch (e) {}
    }
    return () => { try { delete window.__editor_runWorkflow } catch (e) {} }
  }, [saveWorkflow, runWorkflow])

  useEffect(() => {
    try {
      loadWorkflows()
    } catch (e) {}
  }, [loadWorkflows, token])

  useEffect(() => {
    try {
      if (!rfInstanceRef.current || typeof rfInstanceRef.current.fitView !== 'function') return
      const t = setTimeout(() => {
        try {
          rfInstanceRef.current.fitView({ padding: 0.12 })
        } catch (e) {}
      }, 50)
      return () => clearTimeout(t)
    } catch (e) {}
  }, [nodes.length, edges.length])

  const rfInstanceRef = useRef(null)

  return (
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
          addSplitInBatches={() => addNode('SplitInBatches', 'action', { input_path: 'input', batch_size: 10, mode: 'serial', concurrency: 4, fail_behavior: 'stop_on_error', max_chunks: '' })}
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

        <TemplatesModal
          open={!!editorState.showTemplates}
          token={token}
          onClose={() => editorDispatch({ type: 'SET_SHOW_TEMPLATES', payload: false })}
          onApply={(graph) => {
            try {
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
            } catch (e) {}
          }}
        />

        <div className="canvas">
          <div className="reactflow-wrapper" style={{ height: '100%', minHeight: 600 }}>
            <ReactFlowProvider>
          <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={NODE_TYPES}
                onNodeClick={(ev, node) => editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: String(node.id) })}
                onSelectionChange={onSelectionChange}
                onInit={(rfi) => { try { rfInstanceRef.current = rfi } catch (e) {} }}
                onLoad={(rfi) => { try { rfInstanceRef.current = rfi } catch (e) {} }}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                zoomOnScroll={true}
                zoomOnPinch={true}
                panOnScroll={true}
                panOnDrag={true}
                minZoom={0.05}
                maxZoom={2}
                fitView={false}
                fitViewOptions={{ padding: 0.12 }}
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
