import React, { useEffect, useState } from 'react'
import TemplatePreview from './TemplatePreview'

export default function TemplatesModal({ open, onClose, onApply, token }) {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!open) return
    let mounted = true
    const load = async () => {
      setLoading(true)
      setErr(null)
      try {
        const headers = {}
        if (token) headers.Authorization = `Bearer ${token}`
        const resp = await fetch('/api/templates', { headers })
        if (!resp.ok) {
          // no backend endpoint — fall back to builtin templates
          throw new Error(`no remote templates: ${resp.status}`)
        }
        const data = await resp.json()
        if (mounted) setTemplates(Array.isArray(data) ? data : [])
      } catch (e) {
        // fallback: provide a small built-in starter template so the UI works
        if (mounted) {
          setErr(String(e))
          setTemplates([
            {
              id: 'starter-1',
              title: 'HTTP -> LLM',
              description: 'Simple pipeline: HTTP request -> LLM processing',
              graph: {
                nodes: [
                  { id: 'n1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'HTTP Trigger', config: {} } },
                  { id: 'n2', type: 'http', position: { x: 180, y: 0 }, data: { label: 'HTTP Request', config: { method: 'GET', url: 'https://api.example.com' } } },
                  { id: 'n3', type: 'llm', position: { x: 360, y: 0 }, data: { label: 'LLM', config: { model: 'gpt' } } },
                ],
                edges: [ { id: 'e1', source: 'n1', target: 'n2' }, { id: 'e2', source: 'n2', target: 'n3' } ]
              }
            }
          ])
        }
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => { mounted = false }
  }, [open, token])

  if (!open) return null

  return (
    <div className="templates-overlay" role="dialog" aria-modal="true">
      <div className="templates-modal">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <h3 style={{ margin: 0 }}>Browse templates</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={onClose} className="secondary">Close</button>
          </div>
        </div>

        <div style={{ marginTop: 8 }}>
          {loading && <div>Loading templates…</div>}
          {!loading && err ? <div style={{ color: 'var(--muted)' }}>Using built-in templates ({String(err)})</div> : null}

          <div className="templates-list" style={{ marginTop: 8 }}>
            {templates.map(t => (
              <div key={t.id} className="template-card">
                <h4>{t.title}</h4>
                <div style={{ fontSize: 13, color: 'var(--muted)' }}>{t.description}</div>
                <div style={{ marginTop: 8 }}>
                  <TemplatePreview graph={t.graph || { nodes: [], edges: [] }} height={140} />
                </div>
                <div className="template-actions">
                  <button onClick={() => { onApply && onApply(t.graph); onClose && onClose() }}>Use template</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
