import React, {useEffect, useState} from 'react'
import { useAuth } from '../contexts/AuthContext'
import SchedulerForm from '../components/SchedulerForm'
import RunHistoryModal from '../components/RunHistoryModal'

export default function Schedulers(){
  const { token } = useAuth()
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [showRunsFor, setShowRunsFor] = useState(null)
  const [message, setMessage] = useState(null)

  const fetchList = () => {
    if (!token) return
    setLoading(true)
    fetch('/api/scheduler', { headers: { Authorization: `Bearer ${token}` }})
      .then(async r=>{
        let data
        try { data = await r.json() } catch (e) { data = null }
        if (!r.ok) {
          const msg = (data && (data.detail || data.message)) || `Request failed with status ${r.status}`
          throw new Error(msg)
        }
        setEntries(Array.isArray(data) ? data : [])
        setLoading(false)
      })
      .catch(err=>{ setError(err.message || 'Failed'); setLoading(false) })
  }

  useEffect(()=>{ fetchList() },[token])

  if (!token) return <div>Please login to view schedulers</div>
  if (loading) return <div>Loading...</div>
  if (error) return <div>Error: {error}</div>

  const onCreate = () => { setEditing(null); setShowForm(true) }
  const onEdit = (s) => { setEditing(s); setShowForm(true) }
  const onDelete = async (s) => {
    if (!window.confirm('Delete this scheduler?')) return
    try {
      const r = await fetch(`/api/scheduler/${s.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error('Failed to delete')
      setMessage('Scheduler deleted')
      fetchList()
    } catch (e) { setMessage(e.message || 'Delete failed') }
  }

  const onFormSaved = (created) => { setShowForm(false); fetchList(); setMessage('Saved') }
  const onFormCancel = () => setShowForm(false)

  return (
    <div>
      <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom: 12}}>
        <h2 style={{margin:0}}>Schedulers</h2>
        <button
          className="btn btn-primary"
          onClick={onCreate}
          style={{padding: '10px 16px', fontSize: 16, fontWeight: 600, borderRadius: 6}}
          aria-label="Create Scheduler"
        >
          + Create Scheduler
        </button>
      </div>

      {message && <div className="flash">{message}</div>}

      <table className="table">
        <thead>
          <tr><th>ID</th><th>Workflow ID</th><th>Schedule</th><th>Active</th><th>Last Run</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {entries.map(e=> (
            <tr key={e.id}>
              <td>{e.id}</td>
              <td>{e.workflow_id}</td>
              <td>{e.schedule}</td>
              <td>{e.active ? 'Yes' : 'No'}</td>
              <td>{e.last_run_at || (e.last_run ? new Date(e.last_run).toLocaleString() : '-')}</td>
              <td>
                <button className="btn btn-small" onClick={()=>onEdit(e)}>Edit</button>
                <button className="btn btn-small" onClick={()=>onDelete(e)}>Delete</button>
                <button className="btn btn-small" onClick={()=>setShowRunsFor(e)}>Runs</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {showForm && <SchedulerForm token={token} existing={editing} onSaved={onFormSaved} onCancel={onFormCancel} />}

      {showRunsFor && (
        <RunHistoryModal token={token} scheduler={showRunsFor} onClose={()=>setShowRunsFor(null)} />
      )}
    </div>
  )
}
