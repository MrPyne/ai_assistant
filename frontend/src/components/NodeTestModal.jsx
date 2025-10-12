import React, { useState } from 'react'

export default function NodeTestModal({ node, token, providers = [], secrets = [], onClose }) {
  const [sampleInput, setSampleInput] = useState('{}')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)
  const [selectedProviderId, setSelectedProviderId] = useState(node && node.data && node.data.config && node.data.config.provider_id ? node.data.config.provider_id : '')
  const [overrideSecretId, setOverrideSecretId] = useState('')

  const authHeaders = () => {
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    return headers
  }

  const runTest = async () => {
    setError(null)
    setResponse(null)
    let parsed = {}
    try {
      parsed = sampleInput ? JSON.parse(sampleInput) : {}
    } catch (e) {
      setError('Invalid JSON sample input')
      return
    }
    setLoading(true)
    try {
      // construct node copy and include provider override if selected. Do not persist.
      const nodeCopy = node && node.data ? { ...(node.data || {}), id: node.id } : {}
      // if user selected a provider override, attach it as provider_id so backend will resolve it for this test
      if (selectedProviderId) {
        nodeCopy.provider_id = Number(selectedProviderId)
      }
      // allow specifying an override secret id for provider (used by backend when resolving provider.secret_id)
      if (overrideSecretId) {
        // attach to provider override config so backend tests can pick it up if implemented
        nodeCopy._override_secret_id = Number(overrideSecretId)
      }

      const payload = { node: nodeCopy, sample_input: parsed }
      const resp = await fetch('/api/node_test', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(payload),
      })
      const txt = await resp.text()
      if (!resp.ok) {
        setError(txt || `HTTP ${resp.status}`)
      } else {
        try {
          const j = JSON.parse(txt || '{}')
          setResponse(j)
        } catch (e) {
          setResponse({ raw: txt })
        }
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  const copyResponse = () => {
    try {
      const txt = JSON.stringify(response, null, 2)
      navigator.clipboard && navigator.clipboard.writeText(txt)
      alert('Response copied to clipboard')
    } catch (e) {
      alert('Failed to copy')
    }
  }

  if (!node) return null

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000 }}>
      <div style={{ width: '820px', maxWidth: '95%', background: '#071028', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8, padding: 16, color: '#e8f0ff' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Test Node: {node.data && node.data.label}</div>
          <div>
            <button onClick={onClose} style={{ marginRight: 8 }} className="secondary">Close</button>
            <button onClick={copyResponse} disabled={!response} className="secondary">Copy</button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <div style={{ marginBottom: 6 }}><strong>Sample input (JSON)</strong></div>
            <textarea value={sampleInput} onChange={(e) => setSampleInput(e.target.value)} style={{ width: '100%', height: 220, marginBottom: 8 }} />
            <div style={{ marginBottom: 8 }}>
              <div style={{ marginBottom: 6 }}><strong>Provider override (optional)</strong></div>
              <div style={{ display: 'flex', gap: 8 }}>
                <select value={selectedProviderId} onChange={(e) => setSelectedProviderId(e.target.value)} style={{ flex: 1 }}>
                  <option value=''>-- Use node provider --</option>
                  {providers.map(p => <option key={p.id} value={p.id}>{p.type} (id:{p.id})</option>)}
                </select>
                <select value={overrideSecretId} onChange={(e) => setOverrideSecretId(e.target.value)} style={{ width: 160 }}>
                  <option value=''>No secret override</option>
                  {secrets.map(s => <option key={s.id} value={s.id}>{s.name} (id:{s.id})</option>)}
                </select>
              </div>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>Overrides applied only for this test and are not persisted.</div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={runTest} disabled={loading} className="btn btn-ghost">{loading ? 'Running…' : 'Run Test'}</button>
              <button onClick={() => setSampleInput('{}')} className="btn btn-ghost">Reset</button>
            </div>
          </div>

          <div>
            <div style={{ marginBottom: 6 }}><strong>Result</strong></div>
            <div style={{ background: 'rgba(0,0,0,0.25)', padding: 8, borderRadius: 6, minHeight: 260, maxHeight: 420, overflow: 'auto' }}>
              {error && <div style={{ color: 'var(--danger)', marginBottom: 8 }}>Error: {error}</div>}
              {!error && !response && <div className="muted">No result yet. Click "Run Test" to execute the node.</div>}
              {response && (
                <div>
                  {response.warnings && response.warnings.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <strong>Warnings:</strong>
                      <ul>
                        {response.warnings.map((w, i) => <li key={i} style={{ color: 'var(--muted)' }}>{w}</li>)}
                      </ul>
                    </div>
                  )}

                  {response.info && <div style={{ marginBottom: 8 }}><strong>Info:</strong> <span className="muted">{response.info}</span></div>}

                  <div>
                    <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{JSON.stringify(response.result || response, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
