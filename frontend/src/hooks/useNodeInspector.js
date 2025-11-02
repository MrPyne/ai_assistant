import React, { useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { useEditorState, useEditorDispatch } from '../state/EditorContext'
import Form from '@rjsf/core'
import validator from '@rjsf/validator-ajv8'
import { getNodeUI } from '../nodeRegistry'

export default function useNodeInspector({
  selectedNode,
  token,
  updateNodeConfig,
  providers,
  nodeOptions,
  autoWireTarget,
  setNodes,
  markDirty,
}) {
  const editorState = useEditorState()
  const editorDispatch = useEditorDispatch()
  const selectedNodeId = editorState.selectedNodeId
  const syncTimer = useRef(null)
  const rjsfDebounce = useRef(null)

  const { register, handleSubmit, reset, watch, setValue } = useForm({ mode: 'onChange' })
  const [modelOptions, setModelOptions] = React.useState([])
  const [nodeSchema, setNodeSchema] = React.useState(null)
  const [uiSchema, setUiSchema] = React.useState(null)
  const [schemaLoading, setSchemaLoading] = React.useState(false)

  const [providerSelected, setProviderSelected] = React.useState(null)

  const handleProviderSelect = (e) => {
    const v = e && e.target ? e.target.value : e
    const pid = v === '' ? null : Number(v) || null
    setProviderSelected(pid)
    try { setValue('provider_id', pid) } catch (err) { }
  }

  // fetch modelOptions when provider changes
  useEffect(() => {
    const providerId = (selectedNode && selectedNode.data && selectedNode.data.config && selectedNode.data.config.provider_id) || providerSelected || null
    if (!providerId) {
      setModelOptions([])
      return
    }
    let abort = false
    ;(async () => {
      try {
        const headers = { 'Content-Type': 'application/json' }
        if (token) headers.Authorization = `Bearer ${token}`
        const r = await fetch(`/api/providers/${providerId}`, { headers })
        if (!r.ok) throw new Error('failed')
        const data = await r.json()
        const ptype = data && data.type
        if (!ptype) {
          setModelOptions([])
          return
        }
        const mr = await fetch(`/api/provider_models/${encodeURIComponent(ptype)}`, { headers })
        if (!mr.ok) throw new Error('failed')
        const mdata = await mr.json()
        if (abort) return
        if (Array.isArray(mdata)) setModelOptions(mdata)
        else setModelOptions([])
      } catch (e) {
        if (abort) return
        setModelOptions([])
      }
    })()
    return () => { abort = true }
  }, [selectedNode && selectedNode.data && selectedNode.data.config && selectedNode.data.config.provider_id, providerSelected, token])

  // fetch node schema for server-driven forms
  useEffect(() => {
    if (!selectedNode || !selectedNode.data || !selectedNode.data.label) {
      setNodeSchema(null)
      setUiSchema(null)
      setSchemaLoading(false)
      return
    }
    let abort = false
    const label = selectedNode.data.label
    setSchemaLoading(true)
    ;(async () => {
      try {
        const headers = { 'Content-Type': 'application/json' }
        if (token) headers.Authorization = `Bearer ${token}`
        const resp = await fetch(`/api/node_schema/${encodeURIComponent(label)}`, { headers })
        if (!resp.ok) {
          if (abort) return
          setNodeSchema(null)
          setUiSchema(null)
          setSchemaLoading(false)
          return
        }
        const js = await resp.json()
        if (abort) return
        if (js && js.properties && Object.keys(js.properties).length > 0) {
          setNodeSchema(js)
          setUiSchema(js.uiSchema || null)
        } else {
          setNodeSchema(null)
          setUiSchema(null)
        }
      } catch (e) {
        if (abort) return
        setNodeSchema(null)
        setUiSchema(null)
      } finally {
        if (!abort) setSchemaLoading(false)
      }
    })()
    return () => { abort = true }
  }, [selectedNode && selectedNode.data && selectedNode.data.label, token])

  // initialize form values based on node label
  useEffect(() => {
    if (!selectedNode) return
    const cfg = (selectedNode.data && selectedNode.data.config) || {}
    const label = selectedNode.data && selectedNode.data.label

    if (label === 'HTTP Request') {
      reset({ method: cfg.method || 'GET', url: cfg.url || '', headersText: JSON.stringify(cfg.headers || {}, null, 2), body: cfg.body || '' })
    } else if (label === 'LLM') {
      reset({ prompt: cfg.prompt || '', provider_id: cfg.provider_id || '', model: cfg.model || '' })
    } else if (label === 'Webhook Trigger') {
      reset({})
    } else if (label === 'Send Email') {
      reset({ to: cfg.to || '', from: cfg.from || '', subject: cfg.subject || '', body: cfg.body || '', provider_id: cfg.provider_id || '' })
    } else if (label === 'Slack Message') {
      reset({ channel: cfg.channel || '', text: cfg.text || '', provider_id: cfg.provider_id || '' })
    } else if (label === 'DB Query') {
      reset({ provider_id: cfg.provider_id || '', query: cfg.query || '' })
    } else if (label === 'Cron Trigger') {
      reset({ cron: cfg.cron || '0 * * * *', timezone: cfg.timezone || 'UTC', enabled: cfg.enabled !== false })
    } else if (label === 'HTTP Trigger') {
      reset({ capture_headers: cfg.capture_headers || false })
    } else if (label === 'Transform') {
      reset({ language: cfg.language || 'jinja', template: cfg.template || '' })
    } else if (label === 'Wait') {
      reset({ seconds: cfg.seconds || 60 })
    } else if (['SplitInBatches', 'Loop', 'Parallel'].includes(label)) {
      reset({
        input_path: cfg.input_path || 'input',
        batch_size: cfg.batch_size || 10,
        mode: cfg.mode || 'serial',
        concurrency: cfg.concurrency || 4,
        fail_behavior: cfg.fail_behavior || 'stop_on_error',
        max_chunks: cfg.max_chunks || ''
      })
    } else {
      reset({ rawJsonText: JSON.stringify(selectedNode.data || {}, null, 2) })
    }
  }, [selectedNode, reset])

  const watched = watch()

  // sync friendly/dedicated forms into node config
  useEffect(() => {
    if (!selectedNode) return
    if (syncTimer.current) clearTimeout(syncTimer.current)
    syncTimer.current = setTimeout(() => {
      try {
        const label = selectedNode.data && selectedNode.data.label
        if (label === 'HTTP Request') {
          const method = watched.method || 'GET'
          const url = watched.url || ''
          let headers = {}
          try { headers = JSON.parse(watched.headersText || '{}') } catch (e) { headers = (selectedNode.data.config && selectedNode.data.config.headers) || {} }
          const body = watched.body || ''
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), method, url, headers, body })
          markDirty()
        } else if (label === 'LLM') {
          const prompt = watched.prompt || ''
          const provider_id = watched.provider_id ? (Number(watched.provider_id) || null) : null
          const model = watched.model || ''
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), prompt, provider_id, model })
          markDirty()
        } else if (label === 'Send Email') {
          const to = watched.to || ''
          const from = watched.from || ''
          const subject = watched.subject || ''
          const body = watched.body || ''
          const provider_id = watched.provider_id ? (Number(watched.provider_id) || null) : null
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), to, from, subject, body, provider_id })
          markDirty()
        } else if (label === 'Slack Message') {
          const channel = watched.channel || ''
          const text = watched.text || ''
          const provider_id = watched.provider_id ? (Number(watched.provider_id) || null) : null
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), channel, text, provider_id })
          markDirty()
        } else if (label === 'DB Query') {
          const provider_id = watched.provider_id ? (Number(watched.provider_id) || null) : null
          const query = watched.query || ''
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), provider_id, query })
          markDirty()
        } else if (label === 'Cron Trigger') {
          const cron = watched.cron || '0 * * * *'
          const timezone = watched.timezone || 'UTC'
          const enabled = !!watched.enabled
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), cron, timezone, enabled })
          markDirty()
        } else if (label === 'HTTP Trigger') {
          const capture_headers = !!watched.capture_headers
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), capture_headers })
          markDirty()
        } else if (label === 'Transform') {
          const language = watched.language || 'jinja'
          const template = watched.template || ''
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), language, template })
          markDirty()
        } else if (label === 'Wait') {
          const seconds = Number(watched.seconds) || 0
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), seconds })
          markDirty()
        } else if (['SplitInBatches', 'Loop', 'Parallel'].includes(label)) {
          try {
            const input_path = watched.input_path || 'input'
            const batch_size = Number(watched.batch_size) || 1
            const mode = watched.mode === 'parallel' ? 'parallel' : 'serial'
            const concurrency = Number(watched.concurrency) || 1
            const fail_behavior = watched.fail_behavior === 'continue_on_error' ? 'continue_on_error' : 'stop_on_error'
            const max_chunks = watched.max_chunks === '' || watched.max_chunks === undefined ? null : (Number(watched.max_chunks) || null)
            updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), input_path, batch_size, mode, concurrency, fail_behavior, max_chunks })
            markDirty()
          } catch (e) {
            // ignore sync errors
          }
        } else {
          // raw JSON edits handled by onRawChange
        }
      } catch (e) {
        // ignore sync errors
      }
    }, 300)
    return () => { if (syncTimer.current) clearTimeout(syncTimer.current) }
  }, [watched, selectedNodeId, selectedNode])

  // handlers for raw JSON editor and rjsf changes
  const onRawChange = (e) => {
    const v = e.target.value
    try {
      const parsed = JSON.parse(v)
      setNodes((nds) => nds.map(n => n.id === selectedNodeId ? { ...n, data: parsed } : n))
      markDirty()
      setValue('rawJsonText', v)
    } catch (err) {
      // ignore invalid JSON while typing
    }
  }

  const onRjsfChange = ({ formData }) => {
    if (rjsfDebounce.current) clearTimeout(rjsfDebounce.current)
    rjsfDebounce.current = setTimeout(() => {
      try {
        updateNodeConfig(selectedNodeId, { ...(selectedNode.data && selectedNode.data.config ? selectedNode.data.config : {}), ...formData })
        markDirty()
      } catch (e) {
        // ignore
      }
    }, 250)
  }

  const label = selectedNode && selectedNode.data && selectedNode.data.label
  const nodeUi = getNodeUI(label)

  return {
    // form helpers
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    // state
    modelOptions,
    nodeSchema,
    uiSchema,
    schemaLoading,
    providerSelected,
    setProviderSelected,
    // handlers
    handleProviderSelect,
    onRawChange,
    onRjsfChange,
    // context
    editorState,
    editorDispatch,
    selectedNodeId,
    // derived
    label,
    nodeUi,
  }
}
