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
    selectedRunLogs,
    testWebhook,
  } = props

  const editorState = useEditorState()
  const editorDispatch = useEditorDispatch()
  const validationError = editorState.validationError
  const selectedRunDetail = editorState.selectedRunDetail
  const loadingRunDetail = editorState.loadingRunDetail
  const runDetailError = editorState.runDetailError
  const runs = editorState.runs || []
  const selectedLogs = editorState.selectedRunLogs || selectedRunLogs || []

  const toggleRightPanel = () => editorDispatch({ type: 'SET_RIGHT_PANEL_OPEN', payload: !editorState.rightPanelOpen })

  // NodeInspector reads selectedNodeId from EditorContext itself; no need to pass it here

  return (
    <div className="rightpanel" style={{ display: editorState.rightPanelOpen ? 'block' : 'none', width: editorState.rightPanelWidth }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <h3 style={{ margin: 0 }}>Selected Node</h3>
        <button onClick={toggleRightPanel} className="secondary" style={{ marginLeft: 'auto' }}>{editorState.rightPanelOpen ? 'Hide' : 'Show'}</button>
      </div>
      {validationError && (
        <div style={{ background: '#ffe6e6', border: '1px solid #ffcccc', padding: 8, marginBottom: 8 }}>
          <strong>Validation error:</strong> {validationError}
        </div>
      )}

      <NodeInspector
        selectedNode={selectedNode}
        setShowNodeTest={(v) => editorDispatch({ type: 'SET_SHOW_NODE_TEST', payload: v })}
        setNodeTestToken={(t) => editorDispatch({ type: 'SET_NODE_TEST_TOKEN', payload: t })}
        token={token}
        copyWebhookUrl={copyWebhookUrl}
        workflowId={workflowId}
        webhookTestPayload={editorState.webhookTestPayload}
        setWebhookTestPayload={(p) => editorDispatch({ type: 'SET_WEBHOOK_TEST_PAYLOAD', payload: p })}
        testWebhook={testWebhook}
        updateNodeConfig={updateNodeConfig}
        providers={providers}
        nodeOptions={nodeOptions}
        autoWireTarget={autoWireTarget}
        setNodes={setNodes}
        markDirty={markDirty}
      />

      <hr />
      <RunDetail selectedRunDetail={selectedRunDetail} loading={loadingRunDetail} error={runDetailError} onClose={() => editorDispatch({ type: 'SET_SELECTED_RUN_DETAIL', payload: null })} />

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
    </div>
  )
}
