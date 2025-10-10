import React, { useState, useEffect } from 'react'
import { useAuth } from '../contexts/AuthContext'
import SecretRow from '../components/SecretRow'

export default function Secrets(){
  const { token } = useAuth()
  const [secrets, setSecrets] = useState([])
  const [name, setName] = useState('')
  const [value, setValue] = useState('')

  useEffect(() => { if (token) load() }, [token])

  const authHeaders = () => ({ 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) })

  const load = async () => {
    try {
      const resp = await fetch('/api/secrets', { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        setSecrets(data || [])
      }
    } catch (err) {
      console.warn('Failed to load secrets', err)
    }
  }

  const create = async () => {
    if (!name || !value) return alert('name and value required')
    try {
      const resp = await fetch('/api/secrets', { method: 'POST', headers: authHeaders(), body: JSON.stringify({ name, value }) })
      if (resp.ok) {
        alert('Created')
        setName('')
        setValue('')
        await load()
      } else {
        const txt = await resp.text()
        alert('Failed: ' + txt)
      }
    } catch (err) { alert('Failed: ' + String(err)) }
  }

  const del = async (id) => {
    if (!confirm('Delete secret?')) return
    try {
      const resp = await fetch(`/api/secrets/${id}`, { method: 'DELETE', headers: authHeaders() })
      if (resp.ok) {
        await load()
      } else {
        alert('Failed to delete')
      }
    } catch (e) { alert('Failed: ' + String(e)) }
  }

  return (
    <div style={{ padding: 12 }}>
      <h2>Secrets</h2>
      <div style={{ marginBottom: 8 }}>
        <input placeholder='Name' value={name} onChange={(e) => setName(e.target.value)} style={{ marginRight: 6 }} />
        {/* Use a password input so secret values are masked in the UI. This avoids shoulder-surfing
            and is appropriate because the frontend should never be able to read back the stored
            secret value once saved. */}
        <input type='password' autoComplete='new-password' placeholder='Value' value={value} onChange={(e) => setValue(e.target.value)} style={{ marginRight: 6 }} />
        <button onClick={create}>Create</button>
      </div>
      <div>
        {secrets.length === 0 ? (
          <div className="muted">No secrets</div>
        ) : (
          secrets.map((s) => <SecretRow key={s.id} s={s} onDelete={del} />)
        )}
      </div>
    </div>
  )
}
