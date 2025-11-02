import React, {useEffect, useState} from 'react'
import RunsTable from './RunsTable'

export default function RunHistoryModal({ token, scheduler, onClose }){
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)

  useEffect(()=>{ fetchRuns() },[scheduler])

  async function fetchRuns(){
    setLoading(true)
    setError(null)
    try {
      // backend currently exposes GET /api/runs?workflow_id=...
      const r = await fetch(`/api/runs?workflow_id=${scheduler.workflow_id}`, { headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error('Failed to load runs')
      const data = await r.json()
      setRuns(Array.isArray(data.items) ? data.items.filter(it=>it.workflow_id === scheduler.workflow_id) : [])
    } catch (e) { setError(e.message || 'Failed') }
    setLoading(false)
  }

  async function onRetry(run){
    try {
      setMessage(null)
      const r = await fetch(`/api/runs/${run.id}/retry`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error('Retry failed')
      setMessage('Retry enqueued')
      fetchRuns()
    } catch (e) { setMessage(e.message || 'Retry failed') }
  }

  return (
    <div className="modal">
      <div className="modal-content large">
        <h3>Runs for Scheduler {scheduler.id}</h3>
        <div style={{marginBottom: 8}}><button className="btn btn-ghost" onClick={onClose}>Close</button></div>
        {message && <div className="flash">{message}</div>}
        {loading && <div>Loading...</div>}
        {error && <div className="error">{error}</div>}
        {!loading && !error && (
          <RunsTable runs={runs} onRetry={onRetry} />
        )}
      </div>
    </div>
  )
}
