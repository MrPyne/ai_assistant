import React, {useEffect, useState} from 'react'
import { useAuth } from '../contexts/AuthContext'

export default function Schedulers(){
  const { token } = useAuth()
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(()=>{
    if (!token) return
    setLoading(true)
    fetch('/api/scheduler', { headers: { Authorization: `Bearer ${token}` }})
      .then(r=>r.json())
      .then(data=>{ setEntries(data || []); setLoading(false) })
      .catch(err=>{ setError(err.message || 'Failed'); setLoading(false) })
  },[token])

  if (!token) return <div>Please login to view schedulers</div>
  if (loading) return <div>Loading...</div>
  if (error) return <div>Error: {error}</div>

  return (
    <div>
      <h2>Schedulers</h2>
      <table className="table">
        <thead>
          <tr><th>ID</th><th>Workflow ID</th><th>Schedule</th><th>Active</th><th>Last Run</th></tr>
        </thead>
        <tbody>
          {entries.map(e=> (
            <tr key={e.id}>
              <td>{e.id}</td>
              <td>{e.workflow_id}</td>
              <td>{e.schedule}</td>
              <td>{e.active ? 'Yes' : 'No'}</td>
              <td>{e.last_run_at || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
