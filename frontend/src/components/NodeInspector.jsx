import React, { useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { useEditorState, useEditorDispatch } from '../state/EditorContext'

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

  const { register, handleSubmit, reset, watch, setValue } = useForm({ mode: 'onChange' })

  useEffect(() => {
    if (!selectedNode) return
    // initialize form values based on node type/config
    const cfg = (selectedNode.data && selectedNode.data.config) || {}
    if (selectedNode.data && selectedNode.data.label === 'HTTP Request') {
      reset({ method: cfg.method || 'GET', url: cfg.url || '', headersText: JSON.stringify(cfg.headers || {}, null, 2), body: cfg.body || '' })
    } else if (selectedNode.data && selectedNode.data.label === 'LLM') {
      reset({ prompt: cfg.prompt || '', provider_id: cfg.provider_id || '' })
    } else if (selectedNode.data && selectedNode.data.label === 'Webhook Trigger') {
      // webhook doesn't edit node config here, but keep form in sync
      reset({})
    } else {
      // raw config editing handled separately below
      reset({ rawJsonText: JSON.stringify(selectedNode.data || {}, null, 2) })
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
          updateNodeConfig(selectedNodeId, { ...(selectedNode.data.config || {}), prompt, provider_id })
          markDirty()
        } else {
          // for raw JSON edits we don't use this path
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

          <div style={{ fontSize: 12, color: 'var(--muted)' }}>Note: live LLM calls are disabled by default in the backend. Enable via environment flag to make real API calls.</div>
        </div>
      )}

      {(!selectedNode.data || (selectedNode.data && !['HTTP Request', 'LLM', 'Webhook Trigger'].includes(selectedNode.data.label))) && (
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
