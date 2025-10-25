import React, { useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { useEditorState, useEditorDispatch } from '../state/EditorContext'
import { JsonView as JSONTree } from 'react-json-view-lite'
import 'react-json-view-lite/dist/index.css'
import Form from '@rjsf/core'
import validator from '@rjsf/validator-ajv8'
import { getNodeUI } from '../nodeRegistry'

export default function NodeInspector({
  selectedNode,
  token,
  copyWebhookUrl,
  workflowId,
  testWebhook,
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

  useEffect(() => {
    if (!selectedNode) return
    const cfg = (selectedNode.data && selectedNode.data.config) || {}
    const label = selectedNode.data && selectedNode.data.label

    // initialize values for dedicated/friendly forms
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

  if (!selectedNode) return <div className="muted">No node selected. Click a node to view/edit its config.</div>

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

  const label = selectedNode.data && selectedNode.data.label
  const nodeUi = getNodeUI(label)

  return (
    <div>
      <div style={{ marginBottom: 8 }}>Node id: <strong>{selectedNodeId}</strong></div>
      <div style={{ marginBottom: 8 }}>
        <button onClick={() => { editorDispatch({ type: 'SET_SHOW_NODE_TEST', payload: true }); editorDispatch({ type: 'SET_NODE_TEST_TOKEN', payload: token }) }} className="btn btn-ghost">Test Node</button>
      </div>

      {label === 'Webhook Trigger' && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ marginBottom: 6 }}>Webhook trigger node.</div>
          <div style={{ fontSize: 13, marginBottom: 6 }}>After saving the workflow, copy the webhook URL and POST to it to trigger a run.</div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={copyWebhookUrl}>Copy webhook URL</button>
            <button onClick={() => { if (workflowId && selectedNodeId) { const url = `${window.location.origin}/api/webhook/${workflowId}/${selectedNodeId}`; window.open(url, '_blank') } else { alert('Save the workflow first') } }} className="secondary">Open (GET)</button>
          </div>

          <div style={{ marginTop: 8 }}>
            <label style={{ display: 'block', marginBottom: 4 }}>Test payload (JSON)</label>
            <textarea value={editorState.webhookTestPayload} onChange={(e) => editorDispatch({ type: 'SET_WEBHOOK_TEST_PAYLOAD', payload: e.target.value })} style={{ width: '100%', height: 120 }} />
            <div style={{ marginTop: 6, display: 'flex', gap: 6 }}>
              <button onClick={testWebhook}>Send Test (POST)</button>
              <button onClick={() => { editorDispatch({ type: 'SET_WEBHOOK_TEST_PAYLOAD', payload: '{}' }) }} className="secondary">Reset</button>
            </div>
          </div>
        </div>
      )}

      {editorState.validationError && editorState.validationError.length > 0 && (
        <div style={{ marginTop: 8, padding: 8, background: 'rgba(255,230,200,0.6)', borderRadius: 4 }}>
          <div style={{ fontWeight: 600 }}>Validation warnings</div>
          <ul style={{ marginTop: 6 }}>
            {editorState.validationError.map((w, i) => <li key={i} style={{ fontSize: 13 }}>{typeof w === 'string' ? w : JSON.stringify(w)}</li>)}
          </ul>
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)' }}>These are non-blocking warnings from server-side soft validation. The workflow can still be saved and run.</div>
        </div>
      )}

      {['SplitInBatches', 'Loop', 'Parallel'].includes(label) && (
        <div>
          <div style={{ marginBottom: 8, fontWeight: 600 }}>Split / Batch configuration</div>

          <label>Input path (dotted)</label>
          <input {...register('input_path')} style={{ width: '100%', marginBottom: 8 }} />

          <label>Batch size</label>
          <input type="number" {...register('batch_size')} style={{ width: '100%', marginBottom: 8 }} />

          <label>Mode</label>
          <select {...register('mode')} style={{ width: '100%', marginBottom: 8 }}>
            <option value="serial">Serial (default)</option>
            <option value="parallel">Parallel</option>
          </select>

          <label>Concurrency (parallel only)</label>
          <input type="number" {...register('concurrency')} style={{ width: '100%', marginBottom: 8 }} />

          <label>Fail behavior</label>
          <select {...register('fail_behavior')} style={{ width: '100%', marginBottom: 8 }}>
            <option value="stop_on_error">Stop on first error</option>
            <option value="continue_on_error">Continue on error</option>
          </select>

          <label>Max chunks (optional)</label>
          <input type="number" {...register('max_chunks')} style={{ width: '100%', marginBottom: 8 }} />
        </div>
      )}

      {label === 'HTTP Trigger' && (
        <div>
          <label>Capture headers</label>
          <input type="checkbox" {...register('capture_headers')} />
        </div>
      )}

      {label === 'Cron Trigger' && (
        <div>
          <label>Cron expression</label>
          <input {...register('cron')} style={{ width: '100%', marginBottom: 8 }} />
          <label>Timezone</label>
          <input {...register('timezone')} style={{ width: '100%', marginBottom: 8 }} />
          <label>Enabled</label>
          <input type="checkbox" {...register('enabled')} />
        </div>
      )}

      {/* Render friendly component if registry provides one */}
      {nodeUi && nodeUi.kind === 'friendly' && (
        <div>
          {nodeUi.component({ register, providers, selectedNode, handleProviderSelect })}
        </div>
      )}

      {/* If no friendly component and the registry doesn't mark this label as "dedicated",
          attempt server schema rendering. This ensures exactly one editor is shown. */}
      {!nodeUi && (
        <div style={{ marginTop: 8 }}>
          <div style={{ marginBottom: 6, fontWeight: 600 }}>Node data (editable)</div>
          {schemaLoading && <div style={{ fontSize: 12, color: 'var(--muted)' }}>Loading schema...</div>}
          {nodeSchema ? (
            <div>
              <Form
                validator={validator}
                schema={nodeSchema}
                uiSchema={uiSchema || {}}
                formData={(selectedNode.data && (selectedNode.data.config || {}))}
                onChange={onRjsfChange}
                onSubmit={() => {}}
                onError={() => {}}
              >
                <div />
              </Form>
            </div>
          ) : (
            <div>
              <div style={{ marginBottom: 6, fontWeight: 600 }}>Node data (preview)</div>
              <JSONTree data={selectedNode.data} expandDepth={1} />
            </div>
          )}
        </div>
      )}

      {/* Dedicated inline UIs still live here in NodeInspector but are now gated by registry 'dedicated' kind */}
      {nodeUi && nodeUi.kind === 'dedicated' && (
        <>
          {label === 'DB Query' && (
            <div>
              <label>Provider</label>
              <select {...register('provider_id')} onChange={(e)=>{ register && register.onChange ? register.onChange(e) : null; handleProviderSelect(e) }} value={watch().provider_id || (selectedNode.data && selectedNode.data.config && selectedNode.data.config.provider_id) || ''} style={{ width: '100%', marginBottom: 8 }}>
                <option value=''>-- Select provider --</option>
                {providers.map(p => <option key={p.id} value={p.id}>{p.type} (id:{p.id})</option>)}
              </select>
              <label>Query</label>
              <textarea {...register('query')} style={{ width: '100%', height: 140 }} />
            </div>
          )}

          {label === 'Transform' && (
            <div>
              <label>Language</label>
              <select {...register('language')} style={{ width: '100%', marginBottom: 8 }}>
                <option value='jinja'>Jinja</option>
              </select>
              <label>Template</label>
              <textarea {...register('template')} style={{ width: '100%', height: 200 }} />
            </div>
          )}

          {label === 'Wait' && (
            <div>
              <label>Seconds</label>
              <input type="number" {...register('seconds')} style={{ width: '100%' }} />
            </div>
          )}

          {label === 'HTTP Request' && (
            <div>
              <label>Method</label>
              <select {...register('method')} style={{ width: '100%', marginBottom: 8 }}>
                <option>GET</option>
                <option>POST</option>
                <option>PUT</option>
                <option>DELETE</option>
                <option>PATCH</option>
              </select>

              <label>URL</label>
              <input {...register('url')} style={{ width: '100%', marginBottom: 8 }} />

              <label>Headers (JSON)</label>
              <textarea {...register('headersText')} style={{ width: '100%', height: 80, marginBottom: 8 }} />

              <label>Body</label>
              <textarea {...register('body')} style={{ width: '100%', height: 80 }} />
            </div>
          )}

          {label === 'LLM' && (
            <div>
              <label>Prompt</label>
              <textarea {...register('prompt')} style={{ width: '100%', height: 140, marginBottom: 8 }} />

              <label>Provider</label>
              <select {...register('provider_id')} onChange={(e)=>{ register && register.onChange ? register.onChange(e) : null; handleProviderSelect(e) }} value={watch().provider_id || (selectedNode.data && selectedNode.data.config && selectedNode.data.config.provider_id) || ''} style={{ width: '100%', marginBottom: 8 }}>
                <option value=''>-- Select provider --</option>
                {providers.map(p => <option key={p.id} value={p.id}>{p.type} (id:{p.id})</option>)}
              </select>

              <label>Model</label>
              <select {...register('model')} style={{ width: '100%', marginBottom: 8 }}>
                <option value=''>-- use provider default --</option>
                {modelOptions.map(m => <option key={m} value={m}>{m}</option>)}
              </select>

              <div style={{ fontSize: 12, color: 'var(--muted)' }}>Note: live LLM calls are disabled by default in the backend. Enable via environment flag to make real API calls.</div>
            </div>
          )}

          {label === 'Cron Trigger' && (
            <div>
              <label>Cron expression</label>
              <input {...register('cron')} style={{ width: '100%', marginBottom: 8 }} />
              <label>Timezone</label>
              <input {...register('timezone')} style={{ width: '100%', marginBottom: 8 }} />
              <label>Enabled</label>
              <input type="checkbox" {...register('enabled')} />
            </div>
          )}

          {/* Raw JSON editor is still available for nodes not explicitly marked 'dedicated' */}
        </>
      )}

      {(!label || (label && !(getNodeUI(label) && getNodeUI(label).kind === 'dedicated'))) && (
        <div>
          <label>Raw node config (JSON)</label>
          <textarea name="rawJsonText" defaultValue={JSON.stringify(selectedNode.data || {}, null, 2)} onChange={onRawChange} style={{ width: '100%', height: 240 }} />
          {label && ['If', 'Switch', 'Condition'].includes(label) && (
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
