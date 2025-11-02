import React from 'react'

export default function RunsTable({ runs, onRetry }){
  return (
    <table className="table">
      <thead><tr><th>ID</th><th>Workflow</th><th>Status</th><th>Started</th><th>Actions</th></tr></thead>
      <tbody>
        {runs.map(r=> (
          <tr key={r.id}>
            <td>{r.id}</td>
            <td>{r.workflow_id}</td>
            <td>{r.status}</td>
            <td>{formatDate(r.started_at || r.created_at)}</td>
            <td>
              <button className="btn btn-small" onClick={()=>onRetry(r)}>Retry</button>
            </td>
          </tr>
        ))}
        {runs.length === 0 && <tr><td colSpan={5}>No runs</td></tr>}
      </tbody>
    </table>
  )
}

function formatDate(s){
  if (!s) return '-'
  try { return new Date(s).toLocaleString() } catch(e){ return s }
}
