import NodeTestModal from './components/NodeTestModal'
import React, { useCallback, useState, useEffect, useRef } from 'react'
import { useAuth } from './contexts/AuthContext'
import ReactFlow, { addEdge, Background, Controls, ReactFlowProvider, applyNodeChanges, applyEdgeChanges } from 'react-flow-renderer'
import NodeRenderer from './NodeRenderer'
import RightPanel from './components/RightPanel'
import TemplatePreview from './components/TemplatePreview'
import Sidebar from './components/Sidebar'

// Define nodeTypes at module scope so the object identity is stable across renders.
const NODE_TYPES = { default: NodeRenderer, input: NodeRenderer }

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
  const { token, setToken } = useAuth()
  const [workflowId, setWorkflowId] = useState(null)
  const [workflows, setWorkflows] = useState([])
  const [runs, setRuns] = useState([])
  const [selectedRunLogs, setSelectedRunLogs] = useState([])
  const [logEventSource, setLogEventSource] = useState(null)
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
  const [showNodeTest, setShowNodeTest] = useState(false)
  const [nodeTestToken, setNodeTestToken] = useState(localStorage.getItem('authToken') || '')
  const [validationError, setValidationError] = useState(null)
  const [selectedRunDetail, setSelectedRunDetail] = useState(null)
  const [runDetailError, setRunDetailError] = useState(null)
  const [loadingRunDetail, setLoadingRunDetail] = useState(false)
  const [autoSaveEnabled, setAutoSaveEnabled] = useState(false)
  const [saveStatus, setSaveStatus] = useState('idle')
  const [lastSavedAt, setLastSavedAt] = useState(null)
  const autosaveTimer = useRef(null)
  const reactFlowInstance = useRef(null)

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

  const nodeOptions = (excludeId = null) => {
    return nodes.filter(n => n && n.id && n.id !== excludeId).map(n => ({ id: n.id, label: (n.data && n.data.label) || n.id }))
  }

  const TEMPLATES = [
    {
      id: 'tpl_webhook_http',
      name: 'Webhook -> HTTP Request',
      description: 'Trigger via webhook then call an external HTTP API (GET)',
      graph: {
        nodes: [
          { id: 'a', type: 'input', data: { label: 'Webhook Trigger', config: {} }, position: { x: 100, y: 40 } },
          { id: 'b', type: 'default', data: { label: 'HTTP Request', config: { method: 'GET', url: 'https://httpbin.org/get?run={{ run.id }}', headers: {}, body: '' } }, position: { x: 320, y: 40 } },
        ],
        edges: [ { id: 'a-b', source: 'a', target: 'b' } ],
      },
    },
    {
      id: 'tpl_webhook_llm_http',
      name: 'Webhook -> LLM -> HTTP',
      description: 'Webhook triggers an LLM prompt, then POSTs the output to an HTTP endpoint',
      graph: {
        nodes: [
          { id: 'a', type: 'input', data: { label: 'Webhook Trigger', config: {} }, position: { x: 80, y: 20 } },
          { id: 'b', type: 'default', data: { label: 'LLM', config: { prompt: 'Summarize the input: {{ input }}' } }, position: { x: 320, y: 20 } },
          { id: 'c', type: 'default', data: { label: 'HTTP Request', config: { method: 'POST', url: 'https://httpbin.org/post', headers: { 'Content-Type': 'application/json' }, body: '{"summary": "{{ run.output.summary if run.output else \"\" }}"}' } }, position: { x: 560, y: 20 } },
        ],
        edges: [ { id: 'a-b', source: 'a', target: 'b' }, { id: 'b-c', source: 'b', target: 'c' } ],
      },
    },
    {
      id: 'tpl_webhook_if',
      name: 'Webhook -> If (route) -> HTTP',
      description: 'Route based on a condition in the payload (e.g., input.value)',
      graph: {
        nodes: [
          { id: 'a', type: 'input', data: { label: 'Webhook Trigger', config: {} }, position: { x: 80, y: 20 } },
          { id: 'b', type: 'default', data: { label: 'If', config: { expression: '{{ input.value }}', true_target: null, false_target: null } }, position: { x: 320, y: 20 } },
          { id: 'c', type: 'default', data: { label: 'HTTP Request', config: { method: 'POST', url: 'https://httpbin.org/post', headers: {}, body: '{"result":"true branch"}' } }, position: { x: 560, y: -20 } },
          { id: 'd', type: 'default', data: { label: 'HTTP Request', config: { method: 'POST', url: 'https://httpbin.org/post', headers: {}, body: '{"result":"false branch"}' } }, position: { x: 560, y: 60 } },
        ],
        edges: [ { id: 'a-b', source: 'a', target: 'b' }, { id: 'b-c', source: 'b', target: 'c' }, { id: 'b-d', source: 'b', target: 'd' } ],
      },
    },
  ]

  const [showTemplates, setShowTemplates] = useState(false)

  useEffect(() => {
    if (!showTemplates) return
    const handler = (e) => { if (e.key === 'Escape') setShowTemplates(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [showTemplates])

  const loadTemplate = (template) => {
    if (!template || !template.graph) return
    const idMap = {}
    const makeId = (old) => {
      const now = Date.now()
      const id = `${old}-${now.toString(36)}-${Math.random().toString(36).slice(2,8)}`
      return id
    }
    ;(template.graph.nodes || []).forEach(n => { idMap[n.id] = makeId(n.id) })

    const mappedNodes = (template.graph.nodes || []).map(n => ({
      id: idMap[n.id],
      type: n.type === 'input' ? 'input' : 'default',
      position: n.position || { x: 0, y: 0 },
      data: n.data ? { ...n.data, config: { ...(n.data.config || {}) } } : { label: 'Node', config: {} },
      selected: false,
    }))

    const mappedEdges = (template.graph.edges || []).map(e => ({
      id: e.id ? `${e.id}-${Math.random().toString(36).slice(2,8)}` : `${idMap[e.source]}-${idMap[e.target]}`,
      source: idMap[e.source],
      target: idMap[e.target],
    }))

    setWorkflowId(null)
    setWorkflowName(template.name || 'Template')
    setNodes(mappedNodes)
    setEdges(mappedEdges)
    setSelectedNodeId(null)
    setSaveStatus('dirty')
    setLastSavedAt(null)
    markDirty()
  }

  const autoWireTarget = (fromId, toId) => {
    if (!fromId || !toId) return
    const edgeId = `${fromId}-${toId}`
    setEdges((eds) => {
      if (eds.some(e => e.source === fromId && e.target === toId)) return eds
      return eds.concat({ id: edgeId, source: String(fromId), target: String(toId) })
    })
  }

  const loadSecrets = async () => {
    try {
      const resp = await fetch('/api/secrets', { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        setSecrets(data || [])
      }
    } catch (err) {
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

  const onNodesChange = useCallback((changes) => {
    setNodes((nds) => applyNodeChanges(changes, nds))
    markDirty()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const onEdgesChange = useCallback((changes) => {
    setEdges((eds) => applyEdgeChanges(changes, eds))
    markDirty()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onConnect = useCallback((params) => { setEdges((eds) => addEdge(params, eds)); markDirty() }, [])

  const addNode = ({ label = 'Node', config = {}, preferY = 120 }) => {
    setNodes((prevNodes) => {
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
      } catch (err) {}

      const node = {
        id,
        type: label === 'Webhook Trigger' ? 'input' : 'default',
        data: { label, config: config || {} },
        position,
        selected: true,
      }

      console.debug('editor:add_node', { type: label.toLowerCase(), id })

      const cleared = prevNodes.map((n) => (n.selected ? { ...n, selected: false } : n))
      setTimeout(() => setSelectedNodeId(id), 0)
      markDirty()
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

  const addIfNode = () => {
    addNode({ label: 'If', config: { expression: '{{ input.value }}', true_target: null, false_target: null }, preferY: 160 })
  }

  const addSwitchNode = () => {
    addNode({ label: 'Switch', config: { expression: '{{ input.key }}', mapping: {}, default: null }, preferY: 160 })
  }

  const updateNodeConfig = (nodeId, newConfig) => {
    setNodes((nds) => nds.map((n) => {
      if (String(n.id) !== String(nodeId)) return n
      const prevData = n.data && typeof n.data === 'object' ? n.data : {}
      const prevConfig = prevData.config && typeof prevData.config === 'object' ? prevData.config : {}
      const merged = { ...prevData, config: { ...prevConfig, ...(newConfig || {}) } }
      markDirty()
      return { ...n, data: merged }
    }))
  }

  const loadWorkflowGraph = (wf) => {
    if (!wf) return
    setWorkflowId(wf.id)
    if (wf.graph) {
      if (Array.isArray(wf.graph)) {
        const nodesLoaded = wf.graph.filter(e => !e.source && !e.target)
        const edgesLoaded = wf.graph.filter(e => e.source && e.target)
        const sanitize = (n) => ({
          id: String(n.id),
          type: n.type || (n.data && n.data.label === 'Webhook Trigger' ? 'input' : 'default'),
          position: n.position || { x: 0, y: 0 },
          selected: !!n.selected,
          data: n.data && typeof n.data === 'object' ? { ...n.data, config: (n.data.config || {}) } : { label: n.data && n.data.label ? n.data.label : 'Node', config: {} },
        })
        setNodes(nodesLoaded.map(sanitize))
        setEdges((edgesLoaded || []).map(e => ({ ...e, id: e.id ? String(e.id) : `${e.source}-${e.target}`, source: String(e.source), target: String(e.target) })))
        setSelectedNodeId(null)
      } else if (wf.graph.nodes) {
        const sanitize = (n) => ({
          id: String(n.id),
          type: n.type || (n.data && n.data.label === 'Webhook Trigger' ? 'input' : 'default'),
          position: n.position || { x: 0, y: 0 },
          selected: !!n.selected,
          data: n.data && typeof n.data === 'object' ? { ...n.data, config: (n.data.config || {}) } : { label: n.data && n.data.label ? n.data.label : 'Node', config: {} },
        })
        setNodes((wf.graph.nodes || []).map(sanitize))
        setEdges(((wf.graph.edges || [])).map(e => ({ ...e, id: e.id ? String(e.id) : `${e.source}-${e.target}`, source: String(e.source), target: String(e.target) })))
        if (wf.graph.selected_node_id) {
          const exists = ((wf.graph.nodes || []).map(n => String(n.id))).includes(String(wf.graph.selected_node_id))
          setSelectedNodeId(exists ? String(wf.graph.selected_node_id) : null)
        } else {
          setSelectedNodeId(null)
        }
      }
    }
    if (wf.name) setWorkflowName(wf.name)
    setSaveStatus('saved')
    setLastSavedAt(new Date())
  }

  const saveWorkflow = async ({ silent = false } = {}) => {
    const payload = {
      name: workflowName || 'Untitled',
      graph: { nodes, edges, selected_node_id: selectedNodeId },
    }

    setSaveStatus('saving')
    try {
      let resp
      if (workflowId) {
        resp = await fetch(`/api/workflows/${workflowId}`, {
          method: 'PUT',
          headers: authHeaders(),
          body: JSON.stringify(payload),
        })
      } else {
        resp = await fetch('/api/workflows', {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify(payload),
        })
      }

      if (resp.ok) {
        const data = await resp.json()
        if (data && data.id) setWorkflowId(data.id)
        setValidationError(null)
        setSaveStatus('saved')
        setLastSavedAt(new Date())
        await loadWorkflows()
        if (!silent) alert('Saved')
        return true
      } else {
        let detail = null
        try {
          const j = await resp.json()
          detail = j && (j.detail || j.message || JSON.stringify(j))
        } catch (e) {
          try { detail = await resp.text() } catch (e2) { detail = String(e) }
        }

        let nodeToSelect = null
        if (detail && typeof detail === 'object') {
          nodeToSelect = detail.node_id || detail.id || null
          detail = detail.message || detail.detail || JSON.stringify(detail)
        }

        if (!nodeToSelect && typeof detail === 'string') {
          const httpMatch = detail.match(/http node (\S+)/i)
          const llmMatch = detail.match(/llm node (\S+)/i)
          const idxMatch = detail.match(/node at index (\d+)/i)
          const missingIdMatch = detail.match(/missing id/i)

          if (httpMatch) nodeToSelect = httpMatch[1]
          else if (llmMatch) nodeToSelect = llmMatch[1]
          else if (idxMatch) {
            const idx = parseInt(idxMatch[1], 10)
            if (!Number.isNaN(idx) && nodes && nodes.length > idx) {
              nodeToSelect = String(nodes[idx].id)
            }
          } else if (missingIdMatch) {
            const bad = nodes.find(n => n == null || n.id == null || String(n.id).trim() === '')
            if (bad) nodeToSelect = String(bad.id)
          }
        }

        setValidationError(detail)
        setSaveStatus('error')
        if (nodeToSelect) {
          setSelectedNodeId(String(nodeToSelect))
          setNodes((nds) => nds.map(n => (String(n.id) === String(nodeToSelect) ? { ...n, data: { ...(n.data || {}), __validation_error: true } } : n)))
        }
        if (!silent) alert('Save failed: ' + (detail || 'Unknown error'))
        return false
      }
    } catch (err) {
      setSaveStatus('error')
      if (!silent) alert('Save failed: ' + String(err))
      return false
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
          if (!workflowId) selectWorkflow(wf.id)
        }
      } else {
        const txt = await resp.text()
        alert('Failed to load workflows: ' + txt)
      }
    } catch (err) {
      alert('Failed to load workflows: ' + String(err))
    }
  }

  const selectWorkflow = async (id) => {
    if (!id) return
    try {
      const resp = await fetch(`/api/workflows/${id}`, { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        loadWorkflowGraph(data)
      } else {
        const txt = await resp.text()
        alert('Failed to load workflow: ' + txt)
      }
    } catch (err) {
      alert('Failed to load workflow: ' + String(err))
    }
  }

  const newWorkflow = () => {
    setWorkflowId(null)
    setWorkflowName('New Workflow')
    setNodes(initialNodes)
    setEdges(initialEdges)
    setSelectedNodeId(null)
    setSaveStatus('idle')
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
    try {
      const resp = await fetch(`/api/runs/${runId}/logs`, { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
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

    try {
      if (logEventSourceRef.current) {
        try { logEventSourceRef.current.close() } catch (e) {}
      }
    } catch (e) {}
    logEventSourceRef.current = null
    setLogEventSource(null)

    try {
      const url = token ? `/api/runs/${runId}/stream?access_token=${token}` : `/api/runs/${runId}/stream`
      const es = new EventSource(url)
      es.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data)
          setSelectedRunLogs((prev) => prev.concat([payload]))
        } catch (err) {}
      }
      es.onerror = (err) => {
        try { es.close() } catch (e) {}
        logEventSourceRef.current = null
        setLogEventSource(null)
      }
      logEventSourceRef.current = es
      setLogEventSource(es)
    } catch (err) {}
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
    try {
      const sel = nodes.find(n => n && (n.selected === true || String(n.id) === String(selectedNodeId)))
      if (sel) {
        if (String(sel.id) !== String(selectedNodeId)) setSelectedNodeId(String(sel.id))
      } else {
        if (selectedNodeId) setSelectedNodeId(null)
      }
    } catch (e) {}
  }, [nodes])

  useEffect(() => {
    if (token) {
      loadProviders()
      loadSecrets()
      loadWorkflows()
    }
  }, [])

  useEffect(() => {
    return () => {
      try {
        if (logEventSourceRef.current) {
          logEventSourceRef.current.close()
        }
      } catch (e) {}
      logEventSourceRef.current = null
      setLogEventSource(null)
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    }
  }, [logEventSource])

  const selectedNode = selectedNodeId ? nodes.find(n => String(n.id) === String(selectedNodeId)) : null

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

  const markDirty = () => {
    setSaveStatus('dirty')
    if (autoSaveEnabled) {
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
      autosaveTimer.current = setTimeout(() => {
        saveWorkflow({ silent: true })
      }, 1500)
    }
  }

  return (
    <div className="editor-root">
      <div className="editor-main">
        <Sidebar
          workflowName={workflowName}
          setWorkflowName={(v) => { setWorkflowName(v); markDirty() }}
          saveWorkflow={saveWorkflow}
          autoSaveEnabled={autoSaveEnabled}
          setAutoSaveEnabled={setAutoSaveEnabled}
          saveStatus={saveStatus}
          lastSavedAt={lastSavedAt}
          addHttpNode={addHttpNode}
          addLlmNode={addLlmNode}
          addWebhookTrigger={addWebhookTrigger}
          addIfNode={addIfNode}
          addSwitchNode={addSwitchNode}
          setShowTemplates={setShowTemplates}
          token={token}
          setToken={setToken}
          workflowId={workflowId}
          workflows={workflows}
          loadWorkflows={loadWorkflows}
          selectWorkflow={selectWorkflow}
          newWorkflow={newWorkflow}
          runWorkflow={runWorkflow}
          loadRuns={loadRuns}
          providers={providers}
          newProviderType={newProviderType}
          setNewProviderType={setNewProviderType}
          newProviderSecretId={newProviderSecretId}
          setNewProviderSecretId={setNewProviderSecretId}
          createProvider={createProvider}
          secrets={secrets}
          loadSecrets={loadSecrets}
          createSecret={createSecret}
          newSecretName={newSecretName}
          setNewSecretName={setNewSecretName}
          newSecretValue={newSecretValue}
          setNewSecretValue={setNewSecretValue}
          runs={runs}
          viewRunLogs={viewRunLogs}
          viewRunDetail={viewRunDetail}
        />

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
                nodeTypes={NODE_TYPES}
                onInit={(instance) => { reactFlowInstance.current = instance }}
              >
                <Background />
                <Controls />
              </ReactFlow>
            </ReactFlowProvider>
          </div>
        </div>

        <RightPanel
          validationError={validationError}
          selectedNode={selectedNode}
          selectedNodeId={selectedNodeId}
          setShowNodeTest={setShowNodeTest}
          setNodeTestToken={setNodeTestToken}
          token={token}
          copyWebhookUrl={copyWebhookUrl}
          workflowId={workflowId}
          webhookTestPayload={webhookTestPayload}
          setWebhookTestPayload={setWebhookTestPayload}
          testWebhook={testWebhook}
          updateNodeConfig={updateNodeConfig}
          providers={providers}
          nodeOptions={nodeOptions}
          autoWireTarget={autoWireTarget}
          setNodes={setNodes}
          markDirty={markDirty}
          selectedRunDetail={selectedRunDetail}
          loadingRunDetail={loadingRunDetail}
          runDetailError={runDetailError}
          closeRunDetail={closeRunDetail}
          selectedRunLogs={selectedRunLogs}
        />
      </div>
  {showNodeTest && <NodeTestModal node={selectedNode} token={nodeTestToken} providers={providers} secrets={secrets} onClose={() => setShowNodeTest(false)} />}
    {showTemplates && (
      <div className="templates-overlay" onClick={() => setShowTemplates(false)}>
        <div className="templates-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
          <h3>Starter templates</h3>
          <div className="templates-list">
            {TEMPLATES.map(t => (
              <div key={t.id} className="template-card">
                <h4>{t.name}</h4>
                <div style={{ fontSize: 13, color: 'var(--muted)' }}>{t.description}</div>
                <div style={{ marginTop: 8, borderRadius: 8, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.03)', background: 'rgba(0,0,0,0.06)' }}>
                  <div style={{ height: 160 }}>
                    <TemplatePreview graph={t.graph} />
                  </div>
                </div>
                <div className="template-actions">
                  <button onClick={() => { loadTemplate(t); setShowTemplates(false) }}>Load</button>
                  <button className="secondary" onClick={() => setShowTemplates(false)}>Cancel</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )}
    </div>
  )
}
