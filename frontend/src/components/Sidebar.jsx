import ProviderForm from './ProviderForm'
import React, { useEffect, useState } from 'react'
import ProviderEditModal from './ProviderEditModal'
import { useForm, FormProvider, useWatch } from 'react-hook-form'
import { useEditorState, useEditorDispatch } from '../state/EditorContext'

export default function Sidebar({
  saveWorkflow,
  markDirty,
  addHttpNode,
  addLlmNode,
  addWebhookTrigger,
  addHttpTrigger,
  addCronTrigger,
  addSendEmail,
  addSlackMessage,
  addDbQuery,
  addS3Upload,
  addTransform,
  addSplitInBatches,
  addWait,
  addIfNode,
  addSwitchNode,
  // new helper to seed multiple nodes for testing
  seedNodes,
  // setShowTemplates removed; Sidebar now uses EditorContext to show templates
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
  testProvider,
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

  const toggleLeftPanel = () => dispatch({ type: 'SET_LEFT_PANEL_OPEN', payload: !editorState.leftPanelOpen })
  const setActiveTab = (t) => dispatch({ type: 'SET_ACTIVE_LEFT_TAB', payload: t })
  const adjustWidth = (delta) => dispatch({ type: 'SET_LEFT_PANEL_WIDTH', payload: Math.max(200, editorState.leftPanelWidth + delta) })

  // Local selection state for dropdowns
  const [selectedProviderId, setSelectedProviderId] = useState(providers && providers.length ? String(providers[0].id) : '')
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState(null)
  const [selectedSecretId, setSelectedSecretId] = useState(secrets && secrets.length ? String(secrets[0].id) : '')
  const [selectedRunId, setSelectedRunId] = useState(runs && runs.length ? String(runs[0].id) : '')

  useEffect(() => {
    if (providers && providers.length && !providers.find(p => String(p.id) === selectedProviderId)) {
      setSelectedProviderId(String(providers[0].id))
    }
  }, [providers])

  useEffect(() => {
    if (secrets && secrets.length && !secrets.find(s => String(s.id) === selectedSecretId)) {
      setSelectedSecretId(String(secrets[0].id))
    }
  }, [secrets])

  useEffect(() => {
    if (runs && runs.length && !runs.find(r => String(r.id) === selectedRunId)) {
      setSelectedRunId(String(runs[0].id))
    }
  }, [runs])

  // Small inline icon component for SplitInBatches
  const SplitIcon = ({ size = 14 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <rect x="3" y="4" width="18" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <rect x="3" y="14" width="10" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <path d="M15 14L21 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15 10L21 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )

  return (
    <FormProvider {...methods}>
      {/* If panel is open show full content, otherwise render a thin handle to reopen it */}
      {editorState.leftPanelOpen ? (
        <>
        {editModalOpen ? (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60 }}>
            <div style={{ background: 'var(--bg)', padding: 16, borderRadius: 8, width: '90%', maxWidth: 720 }}>
              <h3>Edit Provider</h3>
              {editingProvider ? (
                <ProviderEditModal provider={editingProvider} token={token} onClose={() => { setEditModalOpen(false); setEditingProvider(null); loadProviders && loadProviders() }} loadSecrets={loadSecrets} />
              ) : (
                <div>No provider selected</div>
              )}
              <div style={{ marginTop: 8 }}>
                <button onClick={() => setEditModalOpen(false)}>Close</button>
              </div>
            </div>
          </div>
        ) : null}
        <div className="sidebar" style={{ width: editorState.leftPanelWidth, display: 'flex', flexDirection: 'column' }}>
          <div className="card" style={{ position: 'sticky', top: 0, paddingBottom: 8, zIndex: 5 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className={editorState.activeLeftTab === 'palette' ? 'btn btn-small' : 'secondary btn-small'} onClick={() => setActiveTab('palette')}>Palette</button>
                <button className={editorState.activeLeftTab === 'workflows' ? 'btn btn-small' : 'secondary btn-small'} onClick={() => setActiveTab('workflows')}>Workflows</button>
              </div>
              <div style={{ marginLeft: 8, fontWeight: 600 }}>{editorState.activeLeftTab === 'palette' ? 'Palette' : 'Workflows'}</div>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
              <input className="input" {...methods.register('workflowName')} style={{ flex: 1 }} />
              <button onClick={() => saveWorkflow({ silent: false })} className="btn btn-primary" style={{ padding: '10px 16px', fontSize: 16 }}>Save</button>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input type="checkbox" checked={!!editorState.autoSaveEnabled} onChange={(e) => dispatch({ type: 'SET_AUTOSAVE_ENABLED', payload: e.target.checked })} /> Autosave
              </label>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 'auto' }}>
                {editorState.saveStatus === 'saving' && 'Saving...'}
                {editorState.saveStatus === 'saved' && editorState.lastSavedAt && `Saved ${new Date(editorState.lastSavedAt).toLocaleTimeString()}`}
                {editorState.saveStatus === 'dirty' && 'Unsaved changes'}
                {editorState.saveStatus === 'error' && 'Save error'}
                {editorState.saveStatus === 'idle' && 'Not saved'}
              </div>
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
          {editorState.activeLeftTab === 'palette' ? (
              <div className="palette-buttons">
                <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
                  <button onClick={addHttpNode}>Add HTTP Node</button>
                  <button onClick={addLlmNode}>Add LLM Node</button>
                  <button onClick={addWebhookTrigger}>Add Webhook</button>
                </div>
                <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
                  <button onClick={addHttpTrigger}>Add HTTP Trigger</button>
                  <button onClick={addCronTrigger}>Add Cron Trigger</button>
                  <button onClick={addWait}>Add Wait</button>
                </div>

                {/* Grouped category: Batching */}
                <div style={{ marginBottom: 6 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Batching</div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={addSplitInBatches} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }} aria-label="Add SplitInBatches">
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}><SplitIcon size={14} /></span>
                      <span>SplitInBatches</span>
                    </button>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
                  <button onClick={addSendEmail}>Add Send Email</button>
                  <button onClick={addSlackMessage}>Add Slack Message</button>
                  <button onClick={addDbQuery}>Add DB Query</button>
                </div>
                <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
                  <button onClick={addS3Upload}>Add S3 Upload</button>
                  <button onClick={addTransform}>Add Transform</button>
                </div>
                <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
                  <button onClick={addIfNode}>Add If/Condition</button>
                  <button onClick={addSwitchNode}>Add Switch</button>
                </div>

                <div style={{ marginTop: 8 }}>
                  <label style={{ display: 'block', marginTop: 8 }}>Starter templates</label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                    <button onClick={() => dispatch({ type: 'SET_SHOW_TEMPLATES', payload: true })}>Browse templates...</button>
                  </div>
                </div>

                {/* Seed many nodes for testing */}
                {typeof seedNodes === 'function' ? (
                  <div style={{ marginTop: 10, display: 'flex', gap: 6, alignItems: 'center' }}>
                    <SeedNodesControl seedNodes={seedNodes} />
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {editorState.activeLeftTab === 'workflows' && (
            <>
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
                <button type="button" onClick={loadWorkflows}>Load</button>
                <button type="button" onClick={() => { try { console.debug('Sidebar: Run button clicked') } catch (e) {} ; runWorkflow() }}>Run</button>
                <button type="button" onClick={loadRuns}>Refresh Runs</button>
              </div>

              <hr />
              <h4>Providers</h4>
              <div style={{ marginBottom: 8 }}>
                {/* New provider form */}
                <ProviderForm
                  token={token}
                  secrets={secrets}
                  loadProviders={async () => { try { if (token) await loadProviders(); else await loadProviders() } catch (e) {} }}
                  loadSecrets={loadSecrets}
                  onCreated={(p) => { try { loadProviders(); loadSecrets(); alert('Provider created') } catch (e) {} }}
                />
              </div>

              {/* Providers list converted to a dropdown for compactness */}
              <div style={{ marginBottom: 8 }}>
                <label style={{ display: 'block', marginBottom: 4 }}>Existing providers</label>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <select value={selectedProviderId} onChange={(e) => setSelectedProviderId(e.target.value)} style={{ flex: 1 }}>
                  {providers.length === 0 ? <option value=''>No providers</option> : providers.map(p => <option key={p.id} value={p.id}>{p.type} (id:{p.id})</option>)}
                </select>
                  <button onClick={() => { const p = providers.find(x => String(x.id) === selectedProviderId); if (p) alert(`Provider: ${p.type} (id:${p.id})`)}} className="secondary">Info</button>
                  <button onClick={() => { if (!selectedProviderId) return alert('Select a provider'); testProvider && testProvider(Number(selectedProviderId)) }} className="secondary">Test</button>
                  <button onClick={() => {
                    if (!selectedProviderId) return alert('Select a provider')
                    const p = providers.find(x => String(x.id) === selectedProviderId)
                    if (!p) return alert('Provider not found')
                    setEditingProvider(p)
                    setEditModalOpen(true)
                  }} className="secondary">Edit</button>
                </div>
              </div>

              <hr />
              <h4>Secrets</h4>
              <div style={{ marginBottom: 8, display: 'flex', gap: 6, alignItems: 'center' }}>
                <button onClick={loadSecrets}>Refresh Secrets</button>
                <div style={{ flex: 1 }} />
              </div>

              {/* Secrets list -> dropdown with copy button */}
              <div style={{ marginBottom: 8 }}>
                <label style={{ display: 'block', marginBottom: 4 }}>Existing secrets</label>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <select value={selectedSecretId} onChange={(e) => setSelectedSecretId(e.target.value)} style={{ flex: 1 }}>
                    {secrets.length === 0 ? <option value=''>No secrets</option> : secrets.map(s => <option key={s.id} value={s.id}>{s.name} (id:{s.id})</option>)}
                  </select>
                  <button onClick={() => { navigator.clipboard && navigator.clipboard.writeText(String(selectedSecretId)); alert('Copied id to clipboard') }} className="secondary">Copy id</button>
                </div>
              </div>

              <div style={{ marginTop: 8 }}>
                <input placeholder='Secret name' value={newSecretName} onChange={(e) => setNewSecretName(e.target.value)} style={{ marginBottom: 6 }} />
                <input placeholder='Secret value' value={newSecretValue} onChange={(e) => setNewSecretValue(e.target.value)} style={{ marginBottom: 6 }} />
                <button onClick={createSecret}>Create Secret</button>
              </div>

              <h4 style={{ marginTop: 12 }}>Runs</h4>
              {/* Runs list -> dropdown with action buttons */}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <select value={selectedRunId} onChange={(e) => setSelectedRunId(e.target.value)} style={{ flex: 1 }}>
                  {runs.length === 0 ? <option value=''>No runs</option> : runs.map(r => <option key={r.id} value={r.id}>Run {r.id} — {r.status}</option>)}
                </select>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => viewRunLogs(selectedRunId)} className="secondary">View Logs</button>
                  <button onClick={() => viewRunDetail(selectedRunId)} className="secondary">Details</button>
                </div>
              </div>
            </>
          )}

          {/* bottom controls moved to bottom so they remain visible at the end of the panel */}
          <div className="panel-controls" style={{ marginTop: 'auto', display: 'flex', gap: 6, justifyContent: 'flex-end', paddingTop: 8 }}>
            <button onClick={() => adjustWidth(-20)} className="secondary">-</button>
            <button onClick={() => adjustWidth(20)} className="secondary">+</button>
            <button onClick={toggleLeftPanel} className="secondary">Hide</button>
          </div>
        </div>
      </>) : (
        <div className="sidebar-collapsed" style={{ width: 36 }}>
          <button onClick={toggleLeftPanel} title="Show panel" className="secondary" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>Show</button>
        </div>
      )}
    </FormProvider>
  )
}
function SeedNodesControl({ seedNodes }) {
  const [count, setCount] = React.useState(10)
  return (
    <>
      <label style={{ fontSize: 12 }}>Seed nodes:</label>
      <input type="number" value={count} onChange={(e) => setCount(Number(e.target.value || 0))} style={{ width: 80 }} />
      <button onClick={() => seedNodes(count)}>Seed</button>
    </>
  )
}
