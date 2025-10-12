import React, {useState, useEffect} from 'react'

export default function SchedulerForm({ token, existing, onSaved, onCancel }){
  const [workflowId, setWorkflowId] = useState('')
  const [schedule, setSchedule] = useState('')
  const [description, setDescription] = useState('')
  const [active, setActive] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(()=>{
    if (existing) {
      setWorkflowId(existing.workflow_id)
      setSchedule(existing.schedule)
      setDescription(existing.description || '')
      setActive(!!existing.active)
    }
  },[existing])

  const onSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      if (existing) {
        const r = await fetch(`/api/scheduler/${existing.id}`, { method: 'PUT', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ schedule, description, active }) })
        if (!r.ok) throw new Error('Failed to update')
        onSaved(true)
      } else {
        const r = await fetch('/api/scheduler', { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ workflow_id: Number(workflowId), schedule, description }) })
        if (!r.ok) {
          let data
          try { data = await r.json() } catch(e){ data = null }
          throw new Error((data && (data.detail || data.message)) || 'Failed to create')
        }
        onSaved(true)
      }
    } catch (e) { setError(e.message || 'Save failed') }
    setSaving(false)
  }

  return (
    <div className="modal">
      <div className="modal-content">
        <h3>{existing ? 'Edit' : 'Create'} Scheduler</h3>
        {error && <div className="error">{error}</div>}
        <form onSubmit={onSubmit}>
          {!existing && (
            <div className="form-row">
              <label>Workflow ID</label>
              <input value={workflowId} onChange={e=>setWorkflowId(e.target.value)} />
            </div>
          )}
          <div className="form-row">
            <label>Schedule (seconds or cron)</label>
            <input value={schedule} onChange={e=>setSchedule(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Description (optional)</label>
            <input value={description} onChange={e=>setDescription(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Active</label>
            <input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)} />
          </div>
          <div className="form-row">
            <button className="btn" type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
            <button className="btn btn-ghost" type="button" onClick={onCancel}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}
