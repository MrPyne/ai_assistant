import React from 'react'
import Form from '@rjsf/core'
import validator from '@rjsf/validator-ajv8'
import { JsonView as JSONTree } from 'react-json-view-lite'
import 'react-json-view-lite/dist/index.css'
import { getNodeUI } from '../nodeRegistry'
import useNodeInspector from '../hooks/useNodeInspector'

export default function NodeInspector(props) {
  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    modelOptions,
    nodeSchema,
    uiSchema,
    schemaLoading,
    providerSelected,
    setProviderSelected,
    handleProviderSelect,
    onRawChange,
    onRjsfChange,
    editorState,
    editorDispatch,
    selectedNodeId,
    label,
    nodeUi,
  } = useNodeInspector(props)

  const { selectedNode, token, copyWebhookUrl, workflowId, testWebhook, updateNodeConfig, providers, nodeOptions, autoWireTarget, setNodes, markDirty } = props

  if (!selectedNode) return <div className="muted">No node selected. Click a node to view/edit its config.</div>

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

      {nodeUi && nodeUi.kind === 'friendly' && (
        <div>
          {nodeUi.component({ register, providers, selectedNode, handleProviderSelect })}
        </div>
      )}

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
