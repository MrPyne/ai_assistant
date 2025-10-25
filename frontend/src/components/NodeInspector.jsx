
// NOTE: react-json-view-lite is intentionally small and unsupported compared to react-json-view.
// It's used here only for a read-only preview in NodeInspector. If you prefer a different viewer,
// we can swap it (e.g., react-json-pretty) — this code keeps the API surface minimal.
import React, { useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { useEditorState, useEditorDispatch } from '../state/EditorContext'
import SlackNode from '../nodes/SlackNode'
import EmailNode from '../nodes/EmailNode'
// lightweight React-18-compatible JSON viewer to replace react-json-view
// react-json-view-lite does not provide a default export; import the named
// JsonView export and alias it to JSONTree for compatibility with existing code.
import { JsonView as JSONTree } from 'react-json-view-lite'
import 'react-json-view-lite/dist/index.css'
import Form from '@rjsf/core'
// rjsf v5 removed the built-in AJV validator. Provide a validator implementation
// using the ajv8 validator package. Install with: npm install @rjsf/validator-ajv8
import validator from '@rjsf/validator-ajv8'

// Node component dispatcher: map canonical labels to friendly components.
const NODE_DISPATCH = {
  'Send Email': (props) => <EmailNode {...props} />,
  'Slack Message': (props) => <SlackNode {...props} />,
  // other friendly node types can be added here; fallback to raw editor handled below
}

// Labels that have dedicated UI elsewhere in this component and should NOT
// render the generic RJSF form or the raw JSON editor. Keep nodes that
// intentionally use the raw editor (e.g., If/Switch/Condition) out of this
// set so their auto-wire UI remains available.
const DEDICATED_UI_LABELS = new Set([
  'Send Email',
  'Slack Message',
  'DB Query',
  'Transform',
  'Wait',
  'HTTP Request',
  'LLM',
  'Cron Trigger',
  'HTTP Trigger',
  'SplitInBatches',
  'Loop',
  'Parallel',
  'Webhook Trigger',
])

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
  // read selectedNodeId from EditorContext to avoid prop drilling
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

  // expose a small handler to keep the local provider selection state in sync
  // with the form control. This avoids a race where the model list doesn't
  // refresh because updateNodeConfig hasn't propagated the new provider_id
  // back into selectedNode.data yet.
  const handleProviderSelect = (e) => {
    const v = e && e.target ? e.target.value : e
    const pid = v === '' ? null : Number(v) || null
    setProviderSelected(pid)
    // delegate to react-hook-form to keep its internal state
    try { setValue('provider_id', pid) } catch (err) { }
  }

  // load model list for selected provider when provider changes
  useEffect(() => {
    // prefer the in-form provider selection when present so changing the
    // select updates the model list immediately without waiting for the
    // parent updateNodeConfig round-trip.
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
        // If provider has type info (e.g., 'openai' or 'ollama'), call provider-specific list
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

  // fetch node JSON Schema from server to render rjsf when available
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
        // Only consider a schema useful if it has properties defined
        if (js && js.properties && Object.keys(js.properties).length > 0) {
          setNodeSchema(js)
          // allow server to provide uiSchema via a 'uiSchema' field or UI hints in properties
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
    // initialize form values based on node type/config
    const cfg = (selectedNode.data && selectedNode.data.config) || {}
    if (selectedNode.data && selectedNode.data.label === 'HTTP Request') {
      reset({ method: cfg.method || 'GET', url: cfg.url || '', headersText: JSON.stringify(cfg.headers || {}, null, 2), body: cfg.body || '' })
    } else if (selectedNode.data && selectedNode.data.label === 'LLM') {
      reset({ prompt: cfg.prompt || '', provider_id: cfg.provider_id || '', model: cfg.model || '' })
    } else if (selectedNode.data && selectedNode.data.label === 'Webhook Trigger') {
      // webhook doesn't edit node config here, but keep form in sync
      reset({})
    } else {
      // raw config editing handled separately below
      // support some of the new node types with friendly forms
      if (selectedNode.data && selectedNode.data.label === 'Send Email') {
        reset({ to: cfg.to || '', from: cfg.from || '', subject: cfg.subject || '', body: cfg.body || '', provider_id: cfg.provider_id || '' })
      } else if (selectedNode.data && selectedNode.data.label === 'Slack Message') {
        reset({ channel: cfg.channel || '', text: cfg.text || '', provider_id: cfg.provider_id || '' })
      } else if (selectedNode.data && selectedNode.data.label === 'DB Query') {
        reset({ provider_id: cfg.provider_id || '', query: cfg.query || '' })
      } else if (selectedNode.data && selectedNode.data.label === 'Cron Trigger') {
        reset({ cron: cfg.cron || '0 * * * *', timezone: cfg.timezone || 'UTC', enabled: cfg.enabled !== false })
      } else if (selectedNode.data && selectedNode.data.label === 'HTTP Trigger') {
        reset({ capture_headers: cfg.capture_headers || false })
      } else if (selectedNode.data && selectedNode.data.label === 'Transform') {
        reset({ language: cfg.language || 'jinja', template: cfg.template || '' })
      } else if (selectedNode.data && selectedNode.data.label === 'Wait') {
        reset({ seconds: cfg.seconds || 60 })
      } else if (selectedNode.data && ['SplitInBatches', 'Loop', 'Parallel'].includes(selectedNode.data.label)) {
        // friendly form for batch/split nodes
        reset({
          input_path: cfg.input_path || 'input',
          batch_size: cfg.batch_size || 10,
          mode: cfg.mode || 'serial',
          concurrency: cfg.concurrency || 4,
          fail_behavior: cfg.fail_behavior || 'stop_on_error',
          max_chunks: cfg.max_chunks || ''
        })
      } else {
        // ensure rawJsonText is always present for the raw editor path
        reset({ rawJsonText: JSON.stringify(selectedNode.data || {}, null, 2) })
      }
    }
  }, [selectedNode, reset])


  // watch all fields and debounce syncing to parent updateNodeConfig
  const watched = watch()
  useEffect(() => {
    if (!selectedNode) return
    if (syncTimer.current) clearTimeout(syncTimer.current)
    syncTimer.current = setTimeout(() => {
      try {
        if (selectedNode.data && selectedNode.data.label === 'HTTP Request') {
          const method = watched.method || 'GET'
          const url = watched.url || ''
          let headers = {}
          try { headers = JSON.parse(watched.headersText || '{}') } catch (e) { headers = (selectedNode.data.config && selectedNode.data.config.headers) || {} }
          const body = watched.body || ''
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), method, url, headers, body })
          markDirty()
      } else if (selectedNode.data && selectedNode.data.label === 'LLM') {
          const prompt = watched.prompt || ''
          const provider_id = watched.provider_id ? (Number(watched.provider_id) || null) : null
          const model = watched.model || ''
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), prompt, provider_id, model })
          markDirty()
        } else {
      // sync friendly forms for new node types
      if (selectedNode.data && selectedNode.data.label === 'Send Email') {
        const to = watched.to || ''
        const from = watched.from || ''
        const subject = watched.subject || ''
        const body = watched.body || ''
        const provider_id = watched.provider_id ? (Number(watched.provider_id) || null) : null
        updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), to, from, subject, body, provider_id })
        markDirty()
      } else if (selectedNode.data && selectedNode.data.label === 'Slack Message') {
        const channel = watched.channel || ''
        const text = watched.text || ''
        const provider_id = watched.provider_id ? (Number(watched.provider_id) || null) : null
        updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), channel, text, provider_id })
        markDirty()
      } else if (selectedNode.data && selectedNode.data.label === 'DB Query') {
        const provider_id = watched.provider_id ? (Number(watched.provider_id) || null) : null
        const query = watched.query || ''
        updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), provider_id, query })
        markDirty()
      } else if (selectedNode.data && selectedNode.data.label === 'Cron Trigger') {
        const cron = watched.cron || '0 * * * *'
        const timezone = watched.timezone || 'UTC'
        const enabled = !!watched.enabled
        updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), cron, timezone, enabled })
        markDirty()
      } else if (selectedNode.data && selectedNode.data.label === 'HTTP Trigger') {
        const capture_headers = !!watched.capture_headers
        updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), capture_headers })
        markDirty()
      } else if (selectedNode.data && selectedNode.data.label === 'Transform') {
        const language = watched.language || 'jinja'
        const template = watched.template || ''
        updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), language, template })
        markDirty()
      } else if (selectedNode.data && selectedNode.data.label === 'Wait') {
        const seconds = Number(watched.seconds) || 0
        updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), seconds })
        markDirty()
      } else if (selectedNode.data && ['SplitInBatches', 'Loop', 'Parallel'].includes(selectedNode.data.label)) {
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
        // for raw JSON edits we don't use this path
      }
    }
      } catch (e) {
        // ignore sync errors
      }
    }, 300)
    return () => { if (syncTimer.current) clearTimeout(syncTimer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watched, selectedNodeId, selectedNode])

  if (!selectedNode) return <div className="muted">No node selected. Click a node to view/edit its config.</div>

  const onRawChange = (e) => {
    const v = e.target.value
    try {
      const parsed = JSON.parse(v)
      setNodes((nds) => nds.map(n => n.id === selectedNodeId ? { ...n, data: parsed } : n))
      markDirty()
      // also update form raw text so reset doesn't stomp
      setValue('rawJsonText', v)
    } catch (err) {
      // ignore invalid JSON while typing
    }
  }

  // helper to update config from RJSF with a small debounce to avoid flooding
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

  return (
    <div>
      <div style={{ marginBottom: 8 }}>Node id: <strong>{selectedNodeId}</strong></div>
      <div style={{ marginBottom: 8 }}>
        <button onClick={() => { editorDispatch({ type: 'SET_SHOW_NODE_TEST', payload: true }); editorDispatch({ type: 'SET_NODE_TEST_TOKEN', payload: token }) }} className="btn btn-ghost">Test Node</button>
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
            <textarea value={editorState.webhookTestPayload} onChange={(e) => editorDispatch({ type: 'SET_WEBHOOK_TEST_PAYLOAD', payload: e.target.value })} style={{ width: '100%', height: 120 }} />
            <div style={{ marginTop: 6, display: 'flex', gap: 6 }}>
              <button onClick={testWebhook}>Send Test (POST)</button>
              <button onClick={() => { editorDispatch({ type: 'SET_WEBHOOK_TEST_PAYLOAD', payload: '{}' }) }} className="secondary">Reset</button>
            </div>
          </div>
        </div>
      )}

      {/* If the workflow save produced soft validation warnings, show them here as a non-blocking notice */}
      {editorState.validationError && editorState.validationError.length > 0 && (
        <div style={{ marginTop: 8, padding: 8, background: 'rgba(255,230,200,0.6)', borderRadius: 4 }}>
          <div style={{ fontWeight: 600 }}>Validation warnings</div>
          <ul style={{ marginTop: 6 }}>
            {editorState.validationError.map((w, i) => <li key={i} style={{ fontSize: 13 }}>{typeof w === 'string' ? w : JSON.stringify(w)}</li>)}
          </ul>
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)' }}>These are non-blocking warnings from server-side soft validation. The workflow can still be saved and run.</div>
        </div>
      )}

      {selectedNode.data && ['SplitInBatches', 'Loop', 'Parallel'].includes(selectedNode.data.label) && (
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

      {selectedNode.data && selectedNode.data.label === 'HTTP Trigger' && (
        <div>
          <label>Capture headers</label>
          <input type="checkbox" {...register('capture_headers')} />
        </div>
      )}

      {selectedNode.data && selectedNode.data.label === 'Cron Trigger' && (
        <div>
          <label>Cron expression</label>
          <input {...register('cron')} style={{ width: '100%', marginBottom: 8 }} />
          <label>Timezone</label>
          <input {...register('timezone')} style={{ width: '100%', marginBottom: 8 }} />
          <label>Enabled</label>
          <input type="checkbox" {...register('enabled')} />
        </div>
      )}

      {/* Use dispatcher to render friendly node components when available */}
      {selectedNode.data && NODE_DISPATCH[selectedNode.data.label] && (
        <div>
          {NODE_DISPATCH[selectedNode.data.label]({ register, providers, selectedNode })}
        </div>
      )}

      {/* If no friendly component exists and this label doesn't have a dedicated UI,
          try to render a JSON Schema form from the server. If no schema is available,
          fall back to a read-only JSON preview. This avoids rendering server-driven
          forms (rjsf) for nodes that already have a dedicated UI (e.g., LLM), which
          caused duplicate/conflicting editors. */}
      {selectedNode.data && !NODE_DISPATCH[selectedNode.data.label] && !DEDICATED_UI_LABELS.has(selectedNode.data.label) && (
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

      {selectedNode.data && selectedNode.data.label === 'DB Query' && (
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

      {selectedNode.data && selectedNode.data.label === 'Transform' && (
        <div>
          <label>Language</label>
          <select {...register('language')} style={{ width: '100%', marginBottom: 8 }}>
            <option value='jinja'>Jinja</option>
          </select>
          <label>Template</label>
          <textarea {...register('template')} style={{ width: '100%', height: 200 }} />
        </div>
      )}

      {selectedNode.data && selectedNode.data.label === 'Wait' && (
        <div>
          <label>Seconds</label>
          <input type="number" {...register('seconds')} style={{ width: '100%' }} />
        </div>
      )}

      {selectedNode.data && selectedNode.data.label === 'HTTP Request' && (
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

      {selectedNode.data && selectedNode.data.label === 'LLM' && (
        <div>
          <label>Prompt</label>
          <textarea {...register('prompt')} style={{ width: '100%', height: 140, marginBottom: 8 }} />

          <label>Provider</label>
          <select {...register('provider_id')} style={{ width: '100%', marginBottom: 8 }}>
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

      {(!selectedNode.data || (selectedNode.data && !DEDICATED_UI_LABELS.has(selectedNode.data.label))) && (
        <div>
          <label>Raw node config (JSON)</label>
          <textarea name="rawJsonText" defaultValue={JSON.stringify(selectedNode.data || {}, null, 2)} onChange={onRawChange} style={{ width: '100%', height: 240 }} />
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
