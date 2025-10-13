import React, { useState, useEffect, useRef } from 'react'

export default function ProviderForm({ token, secrets = [], onCreated = null, loadSecrets = null, loadProviders = null }) {
  const FALLBACK_PROVIDER_TYPES = [ 's3', 'smtp', 'openai', 'gcp', 'azure' ]
  const [type, setType] = useState('')
  const [providerTypes, setProviderTypes] = useState([])
  const [providerTypesLoading, setProviderTypesLoading] = useState(true)
  const [providerTypesFallback, setProviderTypesFallback] = useState(false)
  const [schema, setSchema] = useState(null)
  const [formValues, setFormValues] = useState({})
  const [rawJsonMode, setRawJsonMode] = useState(false)
  const [rawJson, setRawJson] = useState('')
  const [selectedSecretId, setSelectedSecretId] = useState('')
  const [isTesting, setIsTesting] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const [message, setMessage] = useState(null)
  const [topError, setTopError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})
  const [showDebug, setShowDebug] = useState(false)
  const initialStateRef = useRef(null)

  useEffect(() => {
    // fetch provider types dynamically from backend; non-blocking fallback
    let abort = false
    ;(async () => {
      try {
        const headers = { 'Content-Type': 'application/json' }
        if (token) headers.Authorization = `Bearer ${token}`
        const r = await fetch('/api/provider_types', { headers })
        if (!r.ok) throw new Error('failed')
        const data = await r.json()
        if (abort) return
        if (Array.isArray(data) && data.length > 0) setProviderTypes(data)
        else setProviderTypes(FALLBACK_PROVIDER_TYPES)
      } catch (e) {
        if (abort) return
        setProviderTypes(FALLBACK_PROVIDER_TYPES)
        setProviderTypesFallback(true)
      } finally {
        if (!abort) setProviderTypesLoading(false)
      }
    })()
    return () => { abort = true }
  // run once on mount
  }, [token])

  useEffect(() => {
    setMessage(null)
    if (!type) {
      setSchema(null)
      return
    }
    // fetch provider schema
    let abort = false
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
        if (abort) return
        setSchema(data)
        // initialize form values for schema properties
        if (data && data.properties) {
          const vals = {}
          Object.keys(data.properties).forEach(k => {
            vals[k] = data.properties[k].default || ''
          })
          setFormValues(vals)
          setRawJson(JSON.stringify(vals, null, 2))
          // record initial snapshot so resets/clears can prompt
          initialStateRef.current = { type, formValues: JSON.parse(JSON.stringify(vals || {})), rawJsonMode: false, rawJson: JSON.stringify(vals, null, 2), selectedSecretId: '' }
        } else {
          // no schema properties — reset form values / raw json
          setFormValues({})
          setRawJson('')
          initialStateRef.current = { type, formValues: {}, rawJsonMode: false, rawJson: '', selectedSecretId: '' }
        }
      } catch (e) {
        if (abort) return
        setSchema(null)
      }
    })()
    return () => { abort = true }
  }, [type, token])

  const updateField = (k, v) => {
    setFormValues((s) => ({ ...s, [k]: v }))
    try { setRawJson(JSON.stringify({ ...formValues, [k]: v }, null, 2)) } catch (e) {}
  }

  // lightweight client-side validation driven by schema
  const validateClient = () => {
    const errs = {}
    if (!type) errs.type = 'Type is required'
    if (schema && schema.properties) {
      const required = schema.required || []
      required.forEach(k => {
        const v = rawJsonMode ? (() => { try { const parsed = JSON.parse(rawJson); return parsed ? parsed[k] : undefined } catch (e) { return undefined } })() : formValues[k]
        if (v === undefined || v === null || v === '') errs[k] = 'Required'
      })
      Object.keys(schema.properties).forEach(k => {
        const prop = schema.properties[k]
        const v = rawJsonMode ? (() => { try { const parsed = JSON.parse(rawJson); return parsed ? parsed[k] : undefined } catch (e) { return undefined } })() : formValues[k]
        if (v === undefined || v === null || v === '') return
        if ((prop.type === 'number' || prop.type === 'integer') && isNaN(Number(v))) errs[k] = 'Must be a number'
        if (prop.pattern) {
          try {
            const re = new RegExp(prop.pattern)
            if (typeof v === 'string' && !re.test(v)) errs[k] = 'Invalid format'
          } catch (e) {}
        }
        if (prop.minLength && typeof v === 'string' && v.length < prop.minLength) errs[k] = `Minimum length ${prop.minLength}`
        if (prop.maxLength && typeof v === 'string' && v.length > prop.maxLength) errs[k] = `Maximum length ${prop.maxLength}`
      })
    }
    return errs
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

  const isDirty = () => {
    const init = initialStateRef.current
    if (!init) return false
    try {
      if (init.type !== type) return true
      if (init.rawJsonMode !== rawJsonMode) return true
      if (rawJsonMode) return init.rawJson !== rawJson
      if ((init.selectedSecretId || '') !== (selectedSecretId || '')) return true
      const a = JSON.stringify(init.formValues || {})
      const b = JSON.stringify(formValues || {})
      return a !== b
    } catch (e) { return true }
  }

  const parseErrorResponse = async (res) => {
    let bodyText = null
    try { bodyText = await res.text() } catch (e) { bodyText = null }
    let parsed = null
    try { parsed = bodyText ? JSON.parse(bodyText) : null } catch (e) { parsed = null }
    if (parsed) {
      if (typeof parsed === 'string') return { top: parsed }
      const top = parsed.detail || parsed.message || parsed.error || (parsed.ok === false ? 'Operation failed' : null)
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
      const clientErrs = validateClient()
      if (Object.keys(clientErrs).length > 0) { setFieldErrors(clientErrs); setIsTesting(false); return }
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

  const doCreate = async () => {
    setMessage(null)
    setTopError(null)
    setFieldErrors({})
    if (!window.confirm('Create this provider?')) return
    setIsCreating(true)
    try {
      const clientErrs = validateClient()
      if (Object.keys(clientErrs).length > 0) { setFieldErrors(clientErrs); setIsCreating(false); return }
      const secretObj = parsedSecret()
      if (!secretObj && !selectedSecretId) {
        setTopError('Provide inline secret or select secret')
        setIsCreating(false)
        return
      }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const body = { type }
      if (secretObj) body.secret = secretObj
      if (!secretObj && selectedSecretId) body.secret_id = Number(selectedSecretId)
      // include non-secret config if not in rawJsonMode
      if (!rawJsonMode) body.config = formValues
      else {
        try { body.config = JSON.parse(rawJson) } catch (e) { /* ignore */ }
      }
      const r = await fetch('/api/providers', { method: 'POST', headers, body: JSON.stringify(body) })
      if (!r.ok) {
        const parsed = await parseErrorResponse(r)
        setTopError(parsed.top || 'Create failed')
        if (parsed.fields) setFieldErrors(parsed.fields)
        setMessage({ type: 'error', text: parsed.top || 'Create failed', raw: parsed.raw })
        setIsCreating(false)
        return
      }
      const data = await r.json()
      setMessage({ type: 'success', text: `Provider created (id: ${data && data.id ? data.id : ''})` })
      try { if (loadProviders) await loadProviders() } catch (e) {}
      try { if (loadSecrets) await loadSecrets() } catch (e) {}
      // update initial snapshot to new clean state
      initialStateRef.current = { type: '', formValues: {}, rawJsonMode: false, rawJson: '', selectedSecretId: '' }
      if (onCreated) onCreated(data)
    } catch (e) { setTopError(String(e)); setMessage({ type: 'error', text: 'Create failed: ' + String(e) }) }
    finally { setIsCreating(false) }
  }

  return (
    <div style={{ border: '1px solid var(--muted)', padding: 8, borderRadius: 6, marginBottom: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <select value={type} onChange={(e) => setType(e.target.value)} style={{ flex: 1 }}>
          <option value=''>Select type...</option>
          {(providerTypes && providerTypes.length ? providerTypes : FALLBACK_PROVIDER_TYPES).map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <button onClick={() => {
          if (isDirty()) {
            if (!window.confirm('You have unsaved changes. Clear anyway?')) return
          }
          setType(''); setSchema(null); setFormValues({}); setRawJson(''); setSelectedSecretId(''); setMessage(null); setTopError(null); setFieldErrors({})
        }} disabled={isCreating || isTesting}>Clear</button>
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

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <div style={{ flex: 1 }}>
            {schema && schema.title ? <div style={{ fontSize: 13, color: 'var(--muted)' }}>{schema.title}</div> : null}
          </div>
        </div>

        <label style={{ display: 'block', marginTop: 8, marginBottom: 6 }}>Secret</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <select value={selectedSecretId} onChange={(e) => setSelectedSecretId(e.target.value)} style={{ minWidth: 160 }} disabled={isCreating || isTesting}>
            <option value=''>No secret</option>
            {secrets.map(s => <option key={s.id} value={s.id}>{s.name} (id:{s.id})</option>)}
          </select>
          <button onClick={() => { setSelectedSecretId(''); setRawJsonMode(false); setFormValues({}); setRawJson('') }} disabled={isCreating || isTesting}>Use inline secret</button>
          <div style={{ flex: 1 }} />
          <button onClick={doTest} disabled={isTesting || isCreating}>{isTesting ? 'Testing...' : 'Test'}</button>
          <button onClick={doCreate} disabled={isCreating || isTesting}>{isCreating ? 'Creating...' : 'Create'}</button>
        </div>

        <div style={{ marginTop: 8 }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={rawJsonMode} onChange={(e) => setRawJsonMode(e.target.checked)} disabled={isCreating || isTesting} /> Raw JSON
          </label>
        </div>

        {rawJsonMode ? (
          <textarea value={rawJson} onChange={(e) => setRawJson(e.target.value)} style={{ width: '100%', height: 140, marginTop: 8 }} placeholder='Enter secret JSON here' disabled={isCreating || isTesting} />
        ) : (
          <div style={{ marginTop: 8 }}>
            {schema && schema.properties ? (
              <div>
                {Object.keys(schema.properties).map((k) => {
                  const prop = schema.properties[k]
                  const isSecret = (prop.format && prop.format === 'password') || (prop.ui && prop.ui.secret) || (prop['ui:widget'] && prop['ui:widget'] === 'password')
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
                        disabled={isCreating || isTesting}
                      />
                      {fieldErrors[k] ? <div style={{ color: 'var(--danger)', fontSize: 12 }}>{fieldErrors[k]}</div> : null}
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
