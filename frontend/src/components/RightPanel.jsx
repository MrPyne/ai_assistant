import React from 'react'
import NodeInspector from './NodeInspector'
import RunDetail from './RunDetail'
import { useEditorState, useEditorDispatch } from '../state/EditorContext'

export default function RightPanel(props) {
  const {
    selectedNode,
    token,
    copyWebhookUrl,
    workflowId,
    updateNodeConfig,
    providers,
    nodeOptions,
    autoWireTarget,
    setNodes,
    markDirty,
    testWebhook,
  } = props

  const editorState = useEditorState()
  const editorDispatch = useEditorDispatch()
  const validationError = editorState.validationError
  const selectedRunDetail = editorState.selectedRunDetail
  const loadingRunDetail = editorState.loadingRunDetail
  const runDetailError = editorState.runDetailError
  const runs = editorState.runs || []
  const selectedLogs = editorState.selectedRunLogs || []
  const toggleRightPanel = () => editorDispatch({ type: 'SET_RIGHT_PANEL_OPEN', payload: !editorState.rightPanelOpen })
  const setActiveTab = (t) => editorDispatch({ type: 'SET_ACTIVE_RIGHT_TAB', payload: t })
  const adjustWidth = (delta) => editorDispatch({ type: 'SET_RIGHT_PANEL_WIDTH', payload: Math.max(200, editorState.rightPanelWidth + delta) })

  // NodeInspector reads selectedNodeId from EditorContext itself; no need to pass it here

  return (
    <div className="rightpanel" style={{ display: editorState.rightPanelOpen ? 'block' : 'none', width: editorState.rightPanelWidth }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className={editorState.activeRightTab === 'inspector' ? 'btn btn-small' : 'secondary btn-small'} onClick={() => setActiveTab('inspector')}>Inspector</button>
          <button className={editorState.activeRightTab === 'runs' ? 'btn btn-small' : 'secondary btn-small'} onClick={() => setActiveTab('runs')}>Runs</button>
        </div>
        <div style={{ marginLeft: 8, fontWeight: 600 }}>{editorState.activeRightTab === 'inspector' ? 'Selected Node' : 'Runs / Logs'}</div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <button onClick={() => adjustWidth(-20)} className="secondary">-</button>
          <button onClick={() => adjustWidth(20)} className="secondary">+</button>
          <button onClick={toggleRightPanel} className="secondary">{editorState.rightPanelOpen ? 'Hide' : 'Show'}</button>
        </div>
      </div>
      {validationError && (
        <div style={{ background: '#ffe6e6', border: '1px solid #ffcccc', padding: 8, marginBottom: 8 }}>
          <strong>Validation error:</strong> {validationError}
        </div>
      )}

      {editorState.activeRightTab === 'inspector' && (
        <NodeInspector
          selectedNode={selectedNode}
          token={token}
          copyWebhookUrl={copyWebhookUrl}
          workflowId={workflowId}
          testWebhook={testWebhook}
          updateNodeConfig={updateNodeConfig}
          providers={providers}
          nodeOptions={nodeOptions}
          autoWireTarget={autoWireTarget}
          setNodes={setNodes}
          markDirty={markDirty}
        />
      )}

      <hr />
      <RunDetail selectedRunDetail={selectedRunDetail} loading={loadingRunDetail} error={runDetailError} onClose={() => editorDispatch({ type: 'SET_SELECTED_RUN_DETAIL', payload: null })} />

      {editorState.activeRightTab === 'runs' && (
        <>
          <hr />
          <h3>Selected Run Logs</h3>
          <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
            {selectedLogs.length === 0 ? <div className="muted">No logs selected</div> : selectedLogs.map(l => (
              <div key={l.id} className="log-entry">
                <div style={{ fontSize: 12, color: 'var(--muted)' }}>{l.timestamp} — {l.node_id} — {l.level}</div>
                <pre>{typeof l.message === 'string' ? l.message : JSON.stringify(l.message, null, 2)}</pre>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
