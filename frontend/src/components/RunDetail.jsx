import React from 'react'

export default function RunDetail({ selectedRunDetail, loading, error, onClose }) {
  const safeStringify = (v) => {
    try {
      if (v === undefined) return 'undefined'
      if (v === null) return 'null'
      if (typeof v === 'string') return v
      return JSON.stringify(v, null, 2)
    } catch (e) {
      return String(v)
    }
  }

  return (
    <div>
      <h3>Run Details</h3>
      <div style={{ maxHeight: '40vh', overflow: 'auto', marginBottom: 8 }}>
        {loading ? (
          <div className="muted">Loading...</div>
        ) : error ? (
          <div className="muted">{error}</div>
        ) : selectedRunDetail ? (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div><strong>Run {selectedRunDetail.id}</strong> — {selectedRunDetail.status}</div>
              <div><button onClick={onClose} className="secondary">Close</button></div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>
              Workflow: {selectedRunDetail.workflow_id} — Attempts: {selectedRunDetail.attempts}
            </div>
            <div style={{ marginTop: 8 }}>
              <div><strong>Input</strong></div>
              <pre style={{ whiteSpace: 'pre-wrap' }}>{safeStringify(selectedRunDetail.input)}</pre>
            </div>
            <div style={{ marginTop: 8 }}>
              <div><strong>Output</strong></div>
              <pre style={{ whiteSpace: 'pre-wrap' }}>{safeStringify(selectedRunDetail.output)}</pre>
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)' }}>
              Created: {selectedRunDetail.created_at || 'n/a'} — Started: {selectedRunDetail.started_at || 'n/a'} — Finished: {selectedRunDetail.finished_at || 'n/a'}
            </div>
            <hr />
            <div><strong>Logs</strong></div>
            {selectedRunDetail.logs && selectedRunDetail.logs.length > 0 ? selectedRunDetail.logs.map(l => (
              <div key={l.id} className="log-entry">
                <div style={{ fontSize: 12, color: 'var(--muted)' }}>{l.timestamp} — {l.node_id} — {l.level}</div>
                <pre>{typeof l.message === 'string' ? l.message : JSON.stringify(l.message, null, 2)}</pre>
              </div>
            )) : <div className="muted">No logs for this run</div>}
          </div>
        ) : (
          <div className="muted">No run selected. Click "Details" in the runs list to load a run.</div>
        )}
      </div>
    </div>
  )
}
