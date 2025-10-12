import React, { useEffect } from 'react'
import { useForm, FormProvider, useWatch } from 'react-hook-form'
import { useEditorState, useEditorDispatch } from '../state/EditorContext'

export default function Sidebar({
  saveWorkflow,
  autoSaveEnabled,
  setAutoSaveEnabled,
  saveStatus,
  lastSavedAt,
  markDirty,
  addHttpNode,
  addLlmNode,
  addWebhookTrigger,
  addIfNode,
  addSwitchNode,
  setShowTemplates,
  token,
  setToken,
  workflowId,
  workflows,
  loadWorkflows,
  selectWorkflow,
  newWorkflow,
  runWorkflow,
  loadRuns,
  providers,
  newProviderType,
  setNewProviderType,
  newProviderSecretId,
  setNewProviderSecretId,
  createProvider,
  secrets,
  loadSecrets,
  createSecret,
  newSecretName,
  setNewSecretName,
  newSecretValue,
  setNewSecretValue,
  runs,
  viewRunLogs,
  viewRunDetail,
}) {
  const editorState = useEditorState()
  const dispatch = useEditorDispatch()

  const methods = useForm({ defaultValues: { workflowName: editorState.workflowName } })

  useEffect(() => {
    methods.reset({ workflowName: editorState.workflowName })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorState.workflowName])

  // Debounced sync to global editor state using useWatch
  const watchedName = useWatch({ control: methods.control, name: 'workflowName' })
  useEffect(() => {
    if (typeof watchedName === 'undefined') return
    if (methods._nameDebounce) clearTimeout(methods._nameDebounce)
    methods._nameDebounce = setTimeout(() => {
      dispatch({ type: 'SET_WORKFLOW_NAME', payload: watchedName })
      dispatch({ type: 'MARK_DIRTY' })
      try { markDirty && markDirty() } catch (e) {}
    }, 300)
    return () => {
      if (methods._nameDebounce) clearTimeout(methods._nameDebounce)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchedName, dispatch])

  return (
    <FormProvider {...methods}>
      <div className="sidebar">
        <div className="card" style={{ position: 'sticky', top: 0, paddingBottom: 8, zIndex: 5 }}>
          <h3>Palette</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <input className="input" {...methods.register('workflowName')} style={{ flex: 1 }} />
            <button onClick={() => saveWorkflow({ silent: false })} className="btn btn-primary" style={{ padding: '10px 16px', fontSize: 16 }}>Save</button>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" checked={autoSaveEnabled} onChange={(e) => setAutoSaveEnabled(e.target.checked)} /> Autosave</label>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 'auto' }}>
              {saveStatus === 'saving' && 'Saving...'}
              {saveStatus === 'saved' && lastSavedAt && `Saved ${new Date(lastSavedAt).toLocaleTimeString()}`}
              {saveStatus === 'dirty' && 'Unsaved changes'}
              {saveStatus === 'error' && 'Save error'}
              {saveStatus === 'idle' && 'Not saved'}
            </div>
          </div>
        </div>

        <div style={{ marginTop: 12 }}>
          <div className="palette-buttons">
            <button onClick={addHttpNode}>Add HTTP Node</button>
            <button onClick={addLlmNode}>Add LLM Node</button>
            <button onClick={addWebhookTrigger}>Add Webhook</button>
            <button onClick={addIfNode}>Add If/Condition</button>
            <button onClick={addSwitchNode}>Add Switch</button>
            <div style={{ marginTop: 8 }}>
              <label style={{ display: 'block', marginTop: 8 }}>Starter templates</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                <button onClick={() => setShowTemplates(true)}>Browse templates...</button>
              </div>
            </div>
          </div>
        </div>

        <hr />
        <div>
          <strong>Auth Token (dev):</strong>
          <input value={token} onChange={(e) => setToken(e.target.value)} placeholder='Paste bearer token here' />
        </div>

        <hr />

        <div className="mt-8">Selected workflow id: {workflowId || 'none'}</div>

        <div style={{ marginTop: 8 }}>
          <label style={{ display: 'block', marginBottom: 4 }}>Workflows</label>
          <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
            <select value={workflowId || ''} onChange={(e) => selectWorkflow(e.target.value)} style={{ flex: 1 }}>
              <option value=''>-- New workflow --</option>
              {workflows.map(w => <option key={w.id} value={w.id}>{w.name || `(id:${w.id})`}</option>)}
            </select>
            <button onClick={loadWorkflows}>Load</button>
            <button onClick={newWorkflow} className="secondary">New</button>
          </div>
        </div>

        <div className="row mt-8">
          <button onClick={loadWorkflows}>Load</button>
          <button onClick={runWorkflow}>Run</button>
          <button onClick={loadRuns}>Refresh Runs</button>
        </div>

        <hr />
        <h4>Providers</h4>
        <div className="row" style={{ marginBottom: 6 }}>
          <input placeholder='Type (e.g. openai)' value={newProviderType} onChange={(e) => setNewProviderType(e.target.value)} style={{ width: '60%', marginRight: 6 }} />
          <select value={newProviderSecretId} onChange={(e) => setNewProviderSecretId(e.target.value)} style={{ width: '30%', marginRight: 6 }}>
            <option value=''>No secret</option>
            {secrets.map(s => <option key={s.id} value={s.id}>{s.name} (id:{s.id})</option>)}
          </select>
          <button onClick={createProvider}>Create Provider</button>
        </div>

        <div className="list-scroll">
          {providers.length === 0 ? <div className="muted">No providers</div> : providers.map(p => (
            <div key={p.id} className="list-item">
              <div><strong>{p.type}</strong> <span className="muted">(id: {p.id})</span></div>
            </div>
          ))}
        </div>

        <hr />
        <h4>Secrets</h4>
        <div style={{ marginBottom: 8 }}>
          <button onClick={loadSecrets}>Refresh Secrets</button>
        </div>
        <div className="list-scroll">
          {secrets.length === 0 ? <div className="muted">No secrets</div> : secrets.map(s => (
            <div key={s.id} className="list-item">
              <div><strong>{s.name}</strong></div>
              <div className="muted">id: {s.id} <button onClick={() => { navigator.clipboard && navigator.clipboard.writeText(String(s.id)); alert('Copied id to clipboard') }} className="secondary">Copy id</button></div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 8 }}>
          <input placeholder='Secret name' value={newSecretName} onChange={(e) => setNewSecretName(e.target.value)} style={{ marginBottom: 6 }} />
          <input placeholder='Secret value' value={newSecretValue} onChange={(e) => setNewSecretValue(e.target.value)} style={{ marginBottom: 6 }} />
          <button onClick={createSecret}>Create Secret</button>
        </div>

        <h4 style={{ marginTop: 12 }}>Runs</h4>
        <div className="list-scroll runs-list">
          {runs.length === 0 ? <div className="muted">No runs</div> : runs.map(r => (
            <div key={r.id} className="run-item">
              <div className="run-meta">Run {r.id} — {r.status}</div>
              <div>
                <button onClick={() => viewRunLogs(r.id)} className="secondary">View Logs</button>
                <button onClick={() => viewRunDetail(r.id)} style={{ marginLeft: 6 }} className="secondary">Details</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </FormProvider>
  )
}
