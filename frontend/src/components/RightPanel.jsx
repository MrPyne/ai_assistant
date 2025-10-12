import React from 'react'
import NodeInspector from './NodeInspector'
import RunDetail from './RunDetail'

export default function RightPanel(props) {
  const {
    validationError,
    selectedNode,
    selectedNodeId,
    setShowNodeTest,
    setNodeTestToken,
    token,
    copyWebhookUrl,
    workflowId,
    webhookTestPayload,
    setWebhookTestPayload,
    testWebhook,
    updateNodeConfig,
    providers,
    nodeOptions,
    autoWireTarget,
    setNodes,
    markDirty,
    selectedRunDetail,
    loadingRunDetail,
    runDetailError,
    closeRunDetail,
    selectedRunLogs,
  } = props

  return (
    <div className="rightpanel">
      <h3>Selected Node</h3>
      {validationError && (
        <div style={{ background: '#ffe6e6', border: '1px solid #ffcccc', padding: 8, marginBottom: 8 }}>
          <strong>Validation error:</strong> {validationError}
        </div>
      )}

      <NodeInspector
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
      />

      <hr />
      <RunDetail selectedRunDetail={selectedRunDetail} loading={loadingRunDetail} error={runDetailError} onClose={closeRunDetail} />

      <hr />
      <h3>Selected Run Logs</h3>
      <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
        {selectedRunLogs.length === 0 ? <div className="muted">No logs selected</div> : selectedRunLogs.map(l => (
          <div key={l.id} className="log-entry">
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>{l.timestamp} — {l.node_id} — {l.level}</div>
            <pre>{typeof l.message === 'string' ? l.message : JSON.stringify(l.message, null, 2)}</pre>
          </div>
        ))}
      </div>
    </div>
  )
}
