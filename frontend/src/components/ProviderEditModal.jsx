import React, { useState, useEffect } from 'react'

export default function ProviderEditModal({ provider, token, onClose = null, loadSecrets = null }) {
  const [type, setType] = useState(provider.type || '')
  const [schema, setSchema] = useState(null)
  const [formValues, setFormValues] = useState({})
  const [rawJsonMode, setRawJsonMode] = useState(false)
  const [rawJson, setRawJson] = useState('')
  const [selectedSecretId, setSelectedSecretId] = useState(provider.secret_id ? String(provider.secret_id) : '')
  const [secrets, setSecrets] = useState([])
  const [message, setMessage] = useState(null)

  useEffect(() => {
    // load schema for type
    if (!type) return
    const load = async () => {
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const r = await fetch(`/api/provider_schema/${encodeURIComponent(type)}`, { headers })
      if (!r.ok) return
      const data = await r.json()
      setSchema(data)
      if (data && data.properties) {
        const vals = {}
        Object.keys(data.properties).forEach(k => {
          vals[k] = data.properties[k].default || ''
        })
        setFormValues(vals)
        setRawJson(JSON.stringify(vals, null, 2))
      }
    }
    load()
  }, [type, token])

  useEffect(() => {
    // load secrets list
    const load = async () => {
      try {
        const headers = {}
        if (token) headers.Authorization = `Bearer ${token}`
        const r = await fetch('/api/secrets', { headers })
        if (!r.ok) return setSecrets([])
        const data = await r.json()
        setSecrets(Array.isArray(data) ? data : [])
      } catch (e) { setSecrets([]) }
    }
    load()
  }, [token])

  const updateField = (k, v) => {
    setFormValues((s) => ({ ...s, [k]: v }))
    try { setRawJson(JSON.stringify({ ...formValues, [k]: v }, null, 2)) } catch (e) {}
  }

  const parsedSecret = () => {
    if (rawJsonMode) {
      try { return JSON.parse(rawJson) } catch (e) { return null }
    }
    return formValues
  }

  const doTest = async () => {
    setMessage(null)
    try {
      const secretObj = parsedSecret()
      if (!secretObj && !selectedSecretId) { setMessage({ type: 'error', text: 'Provide inline secret or select secret' }); return }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const body = { type }
      if (secretObj) body.secret = secretObj
      if (!secretObj && selectedSecretId) body.secret_id = Number(selectedSecretId)
      const r = await fetch('/api/providers/test', { method: 'POST', headers, body: JSON.stringify(body) })
      if (!r.ok) { const txt = await r.text(); setMessage({ type: 'error', text: 'Test failed: ' + txt }); return }
      const data = await r.json()
      if (data && data.ok) setMessage({ type: 'success', text: 'Test succeeded' })
      else setMessage({ type: 'error', text: 'Test failed' })
    } catch (e) { setMessage({ type: 'error', text: 'Test failed: ' + String(e) }) }
  }

  const doUpdate = async () => {
    setMessage(null)
    try {
      const secretObj = parsedSecret()
      const body = { type }
      if (secretObj) body.secret = secretObj
      if (!secretObj && selectedSecretId) body.secret_id = Number(selectedSecretId)
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const r = await fetch(`/api/providers/${provider.id}`, { method: 'PUT', headers, body: JSON.stringify(body) })
      if (!r.ok) { const txt = await r.text(); setMessage({ type: 'error', text: 'Update failed: ' + txt }); return }
      const data = await r.json()
      setMessage({ type: 'success', text: 'Provider updated' })
      if (loadSecrets) await loadSecrets()
      if (onClose) onClose(data)
    } catch (e) { setMessage({ type: 'error', text: 'Update failed: ' + String(e) }) }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input value={type} onChange={(e) => setType(e.target.value)} placeholder='Type' />
        <div style={{ flex: 1 }} />
        <button onClick={doTest}>Test</button>
        <button onClick={doUpdate}>Save</button>
      </div>

      <div style={{ marginTop: 8 }}>
        <label>Secret</label>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select value={selectedSecretId} onChange={(e) => setSelectedSecretId(e.target.value)}>
            <option value=''>No secret</option>
            {secrets.map(s => <option key={s.id} value={s.id}>{s.name} (id:{s.id})</option>)}
          </select>
          <button onClick={() => { setSelectedSecretId(''); setRawJsonMode(false); setFormValues({}); setRawJson('') }}>Use inline secret</button>
        </div>
        <div style={{ marginTop: 8 }}>
          <label><input type='checkbox' checked={rawJsonMode} onChange={(e) => setRawJsonMode(e.target.checked)} /> Raw JSON</label>
        </div>
        {rawJsonMode ? (
          <textarea value={rawJson} onChange={(e) => setRawJson(e.target.value)} style={{ width: '100%', height: 140, marginTop: 8 }} />
        ) : (
          <div style={{ marginTop: 8 }}>
            {schema && schema.properties ? (
              <div>
                {Object.keys(schema.properties).map(k => {
                  const prop = schema.properties[k]
                  const isSecret = (prop.format && prop.format === 'password') || (prop.ui && prop.ui.secret)
                  const val = formValues[k] === undefined ? '' : formValues[k]
                  return (
                    <div key={k} style={{ marginBottom: 6 }}>
                      <label style={{ display: 'block', fontSize: 12 }}>{k}{prop.required ? ' *' : ''}</label>
                      <input type={isSecret ? 'password' : (prop.type === 'boolean' ? 'checkbox' : 'text')} value={prop.type === 'boolean' ? undefined : val} checked={prop.type === 'boolean' ? !!val : undefined} onChange={(e) => { if (prop.type === 'boolean') updateField(k, e.target.checked); else if (prop.type === 'number' || prop.type === 'integer') updateField(k, Number(e.target.value)); else updateField(k, e.target.value) }} style={{ width: '100%' }} />
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className='muted'>No schema available for this provider type</div>
            )}
          </div>
        )}
        {message ? <div style={{ marginTop: 8, color: message.type === 'error' ? 'var(--danger)' : 'var(--success)' }}>{message.text}</div> : null}
      </div>
    </div>
  )
}
