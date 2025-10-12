import React, {useState, useEffect} from 'react'

export default function SchedulerForm({ token, existing, onSaved, onCancel }){
  const [workflowId, setWorkflowId] = useState('')
  const [workflows, setWorkflows] = useState([])
  const [scheduleType, setScheduleType] = useState('interval') // 'interval' or 'cron'
  const [scheduleValue, setScheduleValue] = useState('')
  const [description, setDescription] = useState('')
  const [active, setActive] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(()=>{
    if (existing) {
      setWorkflowId(existing.workflow_id)
      // try to guess schedule type from existing value
      if (existing.schedule && /^[0-9]+$/.test(String(existing.schedule).trim())) {
        setScheduleType('interval')
        setScheduleValue(String(existing.schedule))
      } else {
        setScheduleType('cron')
        setScheduleValue(existing.schedule || '')
      }
      setDescription(existing.description || '')
      setActive(!!existing.active)
    }
  },[existing])

  useEffect(()=>{
    // load workflows so user can pick one by name (friendly dropdown)
    if (!token) return
    const load = async () => {
      try {
        const r = await fetch('/api/workflows', { headers: { Authorization: `Bearer ${token}` }})
        if (!r.ok) return
        const data = await r.json()
        setWorkflows(Array.isArray(data) ? data : [])
      } catch (e) {
        // ignore - workflows list is optional assistance
      }
    }
    load()
  },[token])

  const validateSchedule = () => {
    if (scheduleType === 'interval') {
      const n = Number(scheduleValue)
      if (!Number.isFinite(n) || n <= 0) return 'Interval must be a positive number of seconds'
    } else {
      if (!scheduleValue || scheduleValue.trim().split(' ').length < 3) return 'Please enter a valid cron expression (min 3 space-separated fields)'
    }
    return null
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const vError = validateSchedule()
    if (vError) { setError(vError); setSaving(false); return }

    const schedule = scheduleValue.trim()

    try {
      if (existing) {
        const r = await fetch(`/api/scheduler/${existing.id}`, { method: 'PUT', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ schedule, description, active }) })
        if (!r.ok) throw new Error('Failed to update')
        onSaved(true)
      } else {
        const wfId = Number(workflowId)
        if (!wfId) { throw new Error('Please select a valid workflow') }
        const r = await fetch('/api/scheduler', { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ workflow_id: wfId, schedule, description }) })
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

  // Render as an inline panel that fills available width instead of a modal overlay.
  // This keeps the form in the page flow and makes it expand to the container space.
  return (
    <div style={{marginTop:12}}>
      <div className="card" style={{width:'100%', minHeight: 360}}>
        <h3 style={{marginTop:0}}>{existing ? 'Edit' : 'Create'} Scheduler</h3>
        {error && <div className="error" style={{marginBottom:8, color:'var(--danger)'}}>{error}</div>}
        <form onSubmit={onSubmit}>
          {!existing && (
            <div className="form-row row" style={{alignItems:'center', marginBottom:12}}>
              <div style={{flex:1}}>
                <label className="label">Workflow</label>
                <select className="input" value={workflowId} onChange={e=>setWorkflowId(e.target.value)}>
                  <option value="">-- Select workflow --</option>
                  {workflows.map(w => (
                    <option key={w.id} value={w.id}>{w.id} — {w.name || '(no name)'} </option>
                  ))}
                </select>
                <div className="muted" style={{fontSize:12, marginTop:6}}>Pick the workflow that this scheduler will run. If your workflow isn't listed, create it first in the Workflows page or refresh.</div>
              </div>
            </div>
          )}

          <div className="form-row" style={{marginBottom:12}}>
            <label className="label">Schedule</label>
            <div className="row">
              <div style={{display:'flex',gap:8}}>
                <label style={{display:'flex',alignItems:'center',gap:6}}>
                  <input type="radio" name="sched-type" checked={scheduleType==='interval'} onChange={()=>setScheduleType('interval')} />
                  <span style={{marginLeft:6, fontWeight:600}}>Interval (seconds)</span>
                </label>
                <label style={{display:'flex',alignItems:'center',gap:6}}>
                  <input type="radio" name="sched-type" checked={scheduleType==='cron'} onChange={()=>setScheduleType('cron')} />
                  <span style={{marginLeft:6, fontWeight:600}}>Cron</span>
                </label>
              </div>
            </div>
            <div style={{marginTop:8}}>
              <input className="input" placeholder={scheduleType==='interval' ? 'Example: 3600 (for every hour)' : 'Example: 0 */1 * * * (every hour)'} value={scheduleValue} onChange={e=>setScheduleValue(e.target.value)} />
              <div className="muted" style={{fontSize:12, marginTop:6}}>{scheduleType==='interval' ? 'Enter a number of seconds between runs.' : 'Enter a standard cron expression (min 3 fields). Use an online cron tester if unsure.'}</div>
            </div>
          </div>

          <div className="form-row" style={{marginBottom:12}}>
            <label className="label">Description (optional)</label>
            <input className="input" value={description} onChange={e=>setDescription(e.target.value)} />
          </div>

          <div className="form-row row" style={{alignItems:'center', marginBottom:16}}>
            <div style={{display:'flex',alignItems:'center',gap:10}}>
              <label className="label" style={{margin:0}}>Active</label>
              <input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)} />
            </div>
            <div style={{flex:1}} className="muted">When active is checked the scheduler will trigger runs automatically.</div>
          </div>

          <div className="form-row" style={{display:'flex',gap:8}}>
            <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
            <button className="btn btn-ghost" type="button" onClick={onCancel}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}
