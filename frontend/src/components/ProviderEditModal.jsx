import React, { useState, useEffect, useRef } from 'react'

export default function ProviderEditModal({ provider, token, onClose = null, loadSecrets = null }) {
  const [type, setType] = useState(provider.type || '')
  const [schema, setSchema] = useState(null)
  const [formValues, setFormValues] = useState({})
  const [rawJsonMode, setRawJsonMode] = useState(false)
  const [rawJson, setRawJson] = useState('')
  const [selectedSecretId, setSelectedSecretId] = useState(provider.secret_id ? String(provider.secret_id) : '')
  const [secrets, setSecrets] = useState([])
  const [message, setMessage] = useState(null)
  const [topError, setTopError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})
  const [isTesting, setIsTesting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [existingSecretAttached, setExistingSecretAttached] = useState(!!provider.secret_id)
  const [reenterSecret, setReenterSecret] = useState(false)
  const [providerConfigLoaded, setProviderConfigLoaded] = useState(false)
  const initialStateRef = useRef(null)
  const [showDebug, setShowDebug] = useState(false)

  // load up-to-date provider metadata (config + secret_id)
  useEffect(() => {
    let abort = false
    const loadProvider = async () => {
      try {
        const headers = { 'Content-Type': 'application/json' }
        if (token) headers.Authorization = `Bearer ${token}`
        const r = await fetch(`/api/providers/${provider.id}`, { headers })
        if (!r.ok) {
          // fall back to using passed provider prop
          setProviderConfigLoaded(true)
          return
        }
        const data = await r.json()
        if (abort) return
        if (data) {
          setType(data.type || type)
          // prefer config from server if present
          if (data.config) {
            setFormValues(data.config || {})
            try { setRawJson(JSON.stringify(data.config, null, 2)) } catch (e) { setRawJson('') }
          }
          setSelectedSecretId(data.secret_id ? String(data.secret_id) : '')
          setExistingSecretAttached(!!data.secret_id)
        }
      } catch (e) {
        // ignore
      } finally {
        if (!abort) setProviderConfigLoaded(true)
      }
    }
    loadProvider()
    return () => { abort = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider.id, token])

  // load schema for type
  useEffect(() => {
    if (!type) return
    let abort = false
    const load = async () => {
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      try {
        const r = await fetch(`/api/provider_schema/${encodeURIComponent(type)}`, { headers })
        if (!r.ok) return
        const data = await r.json()
        if (abort) return
        setSchema(data)
        // initialize form values for schema properties only when not already loaded from provider
        if (!providerConfigLoaded) {
          if (data && data.properties) {
            const vals = {}
            Object.keys(data.properties).forEach(k => {
              vals[k] = data.properties[k].default || ''
            })
            setFormValues(vals)
            setRawJson(JSON.stringify(vals, null, 2))
          }
        } else {
          // we have provider config loaded; ensure all schema keys exist in formValues
          if (data && data.properties) {
            setFormValues((prev) => {
              const out = { ...(prev || {}) }
              Object.keys(data.properties).forEach(k => {
                if (out[k] === undefined) out[k] = data.properties[k].default || ''
              })
              try { setRawJson(JSON.stringify(out, null, 2)) } catch (e) {}
              return out
            })
          }
        }
      } catch (e) {
        // ignore
      }
    }
    load()
    return () => { abort = true }
  }, [type, token, providerConfigLoaded])

  // load secrets list
  useEffect(() => {
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
  }, [token, loadSecrets])

  // track initial state for dirty-check
  useEffect(() => {
    const snapshot = { type, formValues: JSON.parse(JSON.stringify(formValues || {})), rawJsonMode, rawJson, selectedSecretId, reenterSecret }
    initialStateRef.current = snapshot
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider.id, providerConfigLoaded])

  const isDirty = () => {
    const init = initialStateRef.current
    if (!init) return false
    try {
      if (init.type !== type) return true
      if (init.rawJsonMode !== rawJsonMode) return true
      if (rawJsonMode) return init.rawJson !== rawJson
      if ((init.selectedSecretId || '') !== (selectedSecretId || '')) return true
      if (init.reenterSecret !== reenterSecret) return true
      // shallow compare JSON of formValues
      const a = JSON.stringify(init.formValues || {})
      const b = JSON.stringify(formValues || {})
      return a !== b
    } catch (e) { return true }
  }

  const updateField = (k, v) => {
    setFormValues((s) => ({ ...s, [k]: v }))
    try { setRawJson(JSON.stringify({ ...formValues, [k]: v }, null, 2)) } catch (e) {}
  }

  const parsedSecret = () => {
    if (rawJsonMode) {
      try { return JSON.parse(rawJson) } catch (e) { return null }
    }
    // if existing secret attached and user is not re-entering, return null so backend will use secret_id
    if (existingSecretAttached && !reenterSecret && selectedSecretId && !rawJsonMode) {
      return null
    }
    // build secret object from schema-driven formValues
    return formValues
  }

  const parseErrorResponse = async (res) => {
    // try to parse JSON body and extract detail/message/field errors
    let bodyText = null
    try { bodyText = await res.text() } catch (e) { bodyText = null }
    let parsed = null
    try { parsed = bodyText ? JSON.parse(bodyText) : null } catch (e) { parsed = null }
    if (parsed) {
      if (typeof parsed === 'string') return { top: parsed }
      // top-level message
      const top = parsed.detail || parsed.message || parsed.error || (parsed.ok === false ? 'Operation failed' : null)
      // field-level mapping
      const fields = {}
      if (parsed.detail && typeof parsed.detail === 'object') {
        Object.keys(parsed.detail).forEach(k => { fields[k] = String(parsed.detail[k]) })
      }
      if (parsed.errors && typeof parsed.errors === 'object') {
        Object.keys(parsed.errors).forEach(k => { fields[k] = String(parsed.errors[k]) })
      }
      return { top: top || null, fields, raw: bodyText }
    }
    return { top: bodyText }
  }

  const doTest = async () => {
    setMessage(null)
    setTopError(null)
    setFieldErrors({})
    setIsTesting(true)
    try {
      const secretObj = parsedSecret()
      if (!secretObj && !selectedSecretId) { setTopError('Provide inline secret or select secret'); setIsTesting(false); return }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const body = { type }
      if (secretObj) body.secret = secretObj
      if (!secretObj && selectedSecretId) body.secret_id = Number(selectedSecretId)
      const r = await fetch('/api/providers/test', { method: 'POST', headers, body: JSON.stringify(body) })
      if (!r.ok) {
        const parsed = await parseErrorResponse(r)
        setTopError(parsed.top || 'Test failed')
        if (parsed.fields) setFieldErrors(parsed.fields)
        setMessage({ type: 'error', text: parsed.top || 'Test failed', raw: parsed.raw })
        setIsTesting(false)
        return
      }
      const data = await r.json()
      if (data && data.ok) setMessage({ type: 'success', text: 'Test succeeded' })
      else setMessage({ type: 'error', text: 'Test failed' })
    } catch (e) { setTopError(String(e)); setMessage({ type: 'error', text: 'Test failed: ' + String(e) }) }
    finally { setIsTesting(false) }
  }

  const doUpdate = async () => {
    setMessage(null)
    setTopError(null)
    setFieldErrors({})
    if (!window.confirm('Save changes to this provider?')) return
    setIsSaving(true)
    try {
      const secretObj = parsedSecret()
      const body = { type }
      if (secretObj) body.secret = secretObj
      if (!secretObj && selectedSecretId) body.secret_id = Number(selectedSecretId)
      // include config (non-secret) so edits to config are persisted
      if (!rawJsonMode) body.config = formValues
      else {
        try { body.config = JSON.parse(rawJson) } catch (e) { /* ignore */ }
      }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const r = await fetch(`/api/providers/${provider.id}`, { method: 'PUT', headers, body: JSON.stringify(body) })
      if (!r.ok) {
        const parsed = await parseErrorResponse(r)
        setTopError(parsed.top || 'Update failed')
        if (parsed.fields) setFieldErrors(parsed.fields)
        setMessage({ type: 'error', text: parsed.top || 'Update failed', raw: parsed.raw })
        setIsSaving(false)
        return
      }
      const data = await r.json()
      setMessage({ type: 'success', text: `Provider updated (id: ${data && data.id ? data.id : provider.id})` })
      // refresh secrets/providers if provided by parent
      try { if (loadSecrets) await loadSecrets() } catch (e) {}
      // set a new initial state to mark clean
      initialStateRef.current = { type, formValues: JSON.parse(JSON.stringify(formValues || {})), rawJsonMode, rawJson, selectedSecretId, reenterSecret }
      // auto-close if caller prefers; otherwise leave open so user can continue
      if (onClose) {
        // small delay so success message can be seen
        setTimeout(() => { onClose && onClose(data) }, 600)
      }
    } catch (e) { setTopError(String(e)); setMessage({ type: 'error', text: 'Update failed: ' + String(e) }) }
    finally { setIsSaving(false) }
  }

  const handleClose = () => {
    if (isDirty()) {
      if (!window.confirm('You have unsaved changes. Discard and close?')) return
    }
    if (onClose) onClose()
  }

  const maskSecretFields = (obj) => {
    if (!obj || !schema || !schema.properties) return obj
    const out = { ...obj }
    Object.keys(schema.properties).forEach(k => {
      const prop = schema.properties[k]
      const isSecret = (prop.format && prop.format === 'password') || (prop.ui && prop.ui.secret)
      if (isSecret && out[k] !== undefined) out[k] = '********'
    })
    return out
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input value={type} onChange={(e) => setType(e.target.value)} placeholder='Type' />
        <div style={{ flex: 1 }} />
        <button onClick={doTest} disabled={isTesting || isSaving}>{isTesting ? 'Testing...' : 'Test'}</button>
        <button onClick={doUpdate} disabled={isSaving}>{isSaving ? 'Saving...' : 'Save'}</button>
        <button onClick={handleClose}>Close</button>
      </div>

      <div style={{ marginTop: 8 }}>
        {/* top-level error banner */}
        {topError ? (
          <div style={{ background: 'var(--danger-bg)', color: 'var(--danger)', padding: 8, borderRadius: 6, marginBottom: 8 }}>
            <div style={{ fontWeight: 600 }}>Error</div>
            <div style={{ fontSize: 13 }}>{topError}</div>
            {message && message.raw ? <div style={{ marginTop: 6 }}><button onClick={() => setShowDebug(!showDebug)} className="secondary">{showDebug ? 'Hide details' : 'Show details'}</button></div> : null}
            {showDebug && message && message.raw ? (<pre style={{ marginTop: 8, background: '#111', color: '#fff', padding: 8, borderRadius: 4 }}>{String(message.raw)}</pre>) : null}
          </div>
        ) : null}

        <label>Secret</label>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select value={selectedSecretId} onChange={(e) => { setSelectedSecretId(e.target.value); setExistingSecretAttached(!!e.target.value); setReenterSecret(false) }}>
            <option value=''>No secret</option>
            {secrets.map(s => <option key={s.id} value={s.id}>{s.name} (id:{s.id})</option>)}
          </select>
          <button onClick={() => { setSelectedSecretId(''); setRawJsonMode(false); setFormValues({}); setRawJson(''); setExistingSecretAttached(false); setReenterSecret(true) }}>Use inline secret (re-enter)</button>
          {existingSecretAttached ? (
            <div style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 8 }}>Existing secret attached (id: {selectedSecretId})</div>
          ) : null}
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

                  // if a secret is attached and user hasn't chosen to re-enter, show masked placeholder
                  if (isSecret && existingSecretAttached && !reenterSecret) {
                    return (
                      <div key={k} style={{ marginBottom: 6 }}>
                        <label style={{ display: 'block', fontSize: 12 }}>{k}{prop.required ? ' *' : ''}</label>
                        <input type='password' value={'********'} readOnly style={{ width: '100%', opacity: 0.6 }} />
                        <div style={{ fontSize: 12, color: 'var(--muted)' }}>
                          An existing secret is attached. Click "Use inline secret (re-enter)" to replace.
                        </div>
                        {fieldErrors[k] ? <div style={{ color: 'var(--danger)', fontSize: 12 }}>{fieldErrors[k]}</div> : null}
                      </div>
                    )
                  }

                  return (
                    <div key={k} style={{ marginBottom: 6 }}>
                      <label style={{ display: 'block', fontSize: 12 }}>{k}{prop.required ? ' *' : ''}</label>
                      <input type={isSecret ? 'password' : (prop.type === 'boolean' ? 'checkbox' : 'text')} value={prop.type === 'boolean' ? undefined : (isSecret ? (val === '********' ? '' : val) : val)} checked={prop.type === 'boolean' ? !!val : undefined} onChange={(e) => { if (prop.type === 'boolean') updateField(k, e.target.checked); else if (prop.type === 'number' || prop.type === 'integer') updateField(k, Number(e.target.value)); else updateField(k, e.target.value) }} style={{ width: '100%' }} />
                      {fieldErrors[k] ? <div style={{ color: 'var(--danger)', fontSize: 12 }}>{fieldErrors[k]}</div> : null}
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

        <div style={{ marginTop: 8 }}>
          <button onClick={() => {
            if (isDirty()) {
              if (!window.confirm('Discard changes and reset form to provider values?')) return
            }
            // reset to loaded provider config
            setSelectedSecretId(provider.secret_id ? String(provider.secret_id) : '')
            setExistingSecretAttached(!!provider.secret_id)
            setReenterSecret(false)
            // refetch provider to reset form values
            (async () => {
              try {
                const headers = { 'Content-Type': 'application/json' }
                if (token) headers.Authorization = `Bearer ${token}`
                const r = await fetch(`/api/providers/${provider.id}`, { headers })
                if (!r.ok) return
                const data = await r.json()
                if (data && data.config) {
                  setFormValues(data.config)
                  try { setRawJson(JSON.stringify(data.config, null, 2)) } catch (e) { setRawJson('') }
                } else {
                  setFormValues({})
                  setRawJson('')
                }
                initialStateRef.current = { type, formValues: JSON.parse(JSON.stringify(formValues || {})), rawJsonMode, rawJson, selectedSecretId, reenterSecret }
              } catch (e) {}
            })()
          }}>Reset</button>
          <button onClick={() => { if (onClose) handleClose() }} style={{ marginLeft: 8 }}>Done</button>
        </div>

      </div>
    </div>
  )
}
