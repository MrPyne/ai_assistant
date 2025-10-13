import React, { useState, useEffect } from 'react'

export default function ProviderForm({ token, secrets = [], onCreated = null, loadSecrets = null, loadProviders = null }) {
  const [type, setType] = useState('')
  const [schema, setSchema] = useState(null)
  const [formValues, setFormValues] = useState({})
  const [rawJsonMode, setRawJsonMode] = useState(false)
  const [rawJson, setRawJson] = useState('')
  const [selectedSecretId, setSelectedSecretId] = useState('')
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    setMessage(null)
    if (!type) {
      setSchema(null)
      return
    }
    // fetch provider schema
    const abort = { aborted: false }
    ;(async () => {
      try {
        const headers = { 'Content-Type': 'application/json' }
        if (token) headers.Authorization = `Bearer ${token}`
        const r = await fetch(`/api/provider_schema/${encodeURIComponent(type)}`, { headers })
        if (!r.ok) {
          setSchema(null)
          return
        }
        const data = await r.json()
        setSchema(data)
        // initialize form values for schema properties
        if (data && data.properties) {
          const vals = {}
          Object.keys(data.properties).forEach(k => {
            vals[k] = data.properties[k].default || ''
          })
          setFormValues(vals)
          setRawJson(JSON.stringify(vals, null, 2))
        }
      } catch (e) {
        if (abort.aborted) return
        setSchema(null)
      }
    })()
    return () => { abort.aborted = true }
  }, [type, token])

  const updateField = (k, v) => {
    setFormValues((s) => ({ ...s, [k]: v }))
    try { setRawJson(JSON.stringify({ ...formValues, [k]: v }, null, 2)) } catch (e) {}
  }

  const parsedSecret = () => {
    if (rawJsonMode) {
      try {
        return JSON.parse(rawJson)
      } catch (e) {
        return null
      }
    }
    // build secret object from schema-driven formValues
    return formValues
  }

  const doTest = async () => {
    setMessage(null)
    setTesting(true)
    try {
      const secretObj = parsedSecret()
      if (!secretObj && !selectedSecretId) {
        setMessage({ type: 'error', text: 'Provide an inline secret (via form or raw JSON) or select an existing secret id' })
        setTesting(false)
        return
      }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const body = { type }
      if (secretObj) body.secret = secretObj
      if (!secretObj && selectedSecretId) body.secret_id = Number(selectedSecretId)
      const r = await fetch('/api/providers/test', { method: 'POST', headers, body: JSON.stringify(body) })
      if (!r.ok) {
        const txt = await r.text()
        setMessage({ type: 'error', text: 'Test failed: ' + txt })
        setTesting(false)
        return
      }
      const data = await r.json()
      if (data && data.ok) {
        setMessage({ type: 'success', text: 'Test succeeded' })
      } else {
        setMessage({ type: 'error', text: 'Test failed' })
      }
    } catch (e) {
      setMessage({ type: 'error', text: 'Test failed: ' + String(e) })
    } finally { setTesting(false) }
  }

  const doCreate = async () => {
    setMessage(null)
    try {
      const secretObj = parsedSecret()
      if (!secretObj && !selectedSecretId) {
        setMessage({ type: 'error', text: 'Provide an inline secret (via form or raw JSON) or select an existing secret id' })
        return
      }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const body = { type }
      if (secretObj) body.secret = secretObj
      if (!secretObj && selectedSecretId) body.secret_id = Number(selectedSecretId)
      const r = await fetch('/api/providers', { method: 'POST', headers, body: JSON.stringify(body) })
      if (!r.ok) {
        const txt = await r.text()
        setMessage({ type: 'error', text: 'Create failed: ' + txt })
        return
      }
      const data = await r.json()
      setMessage({ type: 'success', text: 'Provider created' })
      if (loadProviders) await loadProviders()
      if (loadSecrets) await loadSecrets()
      if (onCreated) onCreated(data)
    } catch (e) {
      setMessage({ type: 'error', text: 'Create failed: ' + String(e) })
    }
  }

  return (
    <div style={{ border: '1px solid var(--muted)', padding: 8, borderRadius: 6, marginBottom: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input placeholder='Type (e.g. openai)' value={type} onChange={(e) => setType(e.target.value)} style={{ flex: 1 }} />
        <button onClick={() => { setType(''); setSchema(null); setFormValues({}); setRawJson('') }}>Clear</button>
      </div>

      <div style={{ marginTop: 8 }}>
        <label style={{ display: 'block', marginBottom: 6 }}>Secret</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <select value={selectedSecretId} onChange={(e) => setSelectedSecretId(e.target.value)} style={{ minWidth: 160 }}>
            <option value=''>No secret</option>
            {secrets.map(s => <option key={s.id} value={s.id}>{s.name} (id:{s.id})</option>)}
          </select>
          <button onClick={() => { setSelectedSecretId(''); setRawJsonMode(false); setFormValues({}); setRawJson('') }}>Use inline secret</button>
          <div style={{ flex: 1 }} />
          <button onClick={doTest} disabled={testing}>{testing ? 'Testing...' : 'Test'}</button>
          <button onClick={doCreate}>Create</button>
        </div>

        <div style={{ marginTop: 8 }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={rawJsonMode} onChange={(e) => setRawJsonMode(e.target.checked)} /> Raw JSON
          </label>
        </div>

        {rawJsonMode ? (
          <textarea value={rawJson} onChange={(e) => setRawJson(e.target.value)} style={{ width: '100%', height: 140, marginTop: 8 }} placeholder='Enter secret JSON here' />
        ) : (
          <div style={{ marginTop: 8 }}>
            {schema && schema.properties ? (
              <div>
                {Object.keys(schema.properties).map((k) => {
                  const prop = schema.properties[k]
                  const isSecret = (prop.format && prop.format === 'password') || (prop.ui && prop.ui.secret)
                  const val = formValues[k] === undefined ? '' : formValues[k]
                  return (
                    <div key={k} style={{ marginBottom: 6 }}>
                      <label style={{ display: 'block', fontSize: 12 }}>{k}{prop.required ? ' *' : ''}</label>
                      <input
                        type={isSecret ? 'password' : (prop.type === 'boolean' ? 'checkbox' : 'text')}
                        value={prop.type === 'boolean' ? undefined : val}
                        checked={prop.type === 'boolean' ? !!val : undefined}
                        onChange={(e) => {
                          if (prop.type === 'boolean') updateField(k, e.target.checked)
                          else if (prop.type === 'number' || prop.type === 'integer') updateField(k, Number(e.target.value))
                          else updateField(k, e.target.value)
                        }}
                        style={{ width: '100%' }}
                      />
                    </div>
                  )
                })}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: 'var(--muted)' }}>No schema available for this provider type — switch to Raw JSON to provide inline secret object.</div>
            )}
          </div>
        )}

        {message ? (
          <div style={{ marginTop: 8, color: message.type === 'error' ? 'var(--danger)' : 'var(--success)' }}>{message.text}</div>
        ) : null}
      </div>
    </div>
  )
}
