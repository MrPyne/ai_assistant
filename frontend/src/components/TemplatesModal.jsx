import React, { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import TemplatePreview from './TemplatePreview'

// Extract TemplateCard to top-level so its identity is stable across
// renders. Defining it inside the TemplatesModal render caused React to
// treat it as a new component type on every render, which forced
// unmount/mount cycles for the TemplatePreview children and produced the
// continuous reload behavior in the small inline previews.
const TemplateCard = React.memo(function TemplateCard({ t, onApply, onClose, setPreview }) {
  return (
    <div key={t.id} className="template-card" style={{ padding: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div>
          <h4 style={{ margin: '2px 0' }}>{t.title}</h4>
          <div style={{ fontSize: 13, color: 'var(--muted)' }}>{t.description}</div>
          <div style={{ marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {(t.tags || []).map(tag => <span key={tag} className="chip" style={{ fontSize: 11 }}>{tag}</span>)}
            {t.category ? <span className="chip" style={{ fontSize: 11 }}>{t.category}</span> : null}
          </div>
        </div>
        <div style={{ minWidth: 120, textAlign: 'right' }}>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>{t.note}</div>
        </div>
      </div>

      {/* Small inline previews removed to avoid inaccurate thumbnails and
          to eliminate remaining rendering differences. The full overlay
          preview (Preview button) still uses TemplatePreview for fidelity. */}
      <div style={{ marginTop: 8, height: 120 }} />

      <div className="template-actions" style={{ marginTop: 8, display: 'flex', gap: 8 }}>
        <button onClick={() => { onApply && onApply(t.graph); onClose && onClose() }}>Use template</button>
        <button onClick={() => {
          try {
            onApply && onApply(t.graph)
            // allow the editor to apply nodes, then call a global run helper
            setTimeout(() => {
              try {
                if (window.__editor_runWorkflow) window.__editor_runWorkflow()
              } catch (e) {}
            }, 120)
          } finally {
            try { onClose && onClose() } catch (e) {}
          }
        }} className="secondary">Load & Run</button>
        <button className="secondary" onClick={() => setPreview(t)}>Preview</button>
      </div>
    </div>
  )
})

// When built-in templates are provided as JSON assets under /templates/
// we attempt to load them from the server. If neither the backend API
// nor the static assets are available we fall back to a tiny builtin
// template so the UI remains usable in tests/CI.
const FALLBACK_TEMPLATES = [
  {
    id: 'starter-1',
    title: 'HTTP -> LLM',
    description: 'Simple pipeline: HTTP request -> LLM processing',
    category: 'Getting started',
    tags: ['http', 'llm', 'starter'],
    note: 'Basic starter: HTTP trigger -> HTTP request -> LLM. Use this to explore saving and running workflows.',
    sample_input: { trigger: { url: 'https://api.example.com' } },
    graph: {
      nodes: [
        { id: 'n1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'HTTP Trigger', config: {} } },
        { id: 'n2', type: 'http', position: { x: 180, y: 0 }, data: { label: 'HTTP Request', config: { method: 'GET', url: 'https://api.example.com' } } },
        { id: 'n3', type: 'llm', position: { x: 360, y: 0 }, data: { label: 'LLM', config: { model: 'gpt' } } },
      ],
      edges: [ { id: 'e1', source: 'n1', target: 'n2' }, { id: 'e2', source: 'n2', target: 'n3' } ]
    }
  }
]

export default function TemplatesModal({ open, onClose, onApply, token }) {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const [tagFilters, setTagFilters] = useState([])
  const [preview, setPreview] = useState(null)
  const [sortBy, setSortBy] = useState('relevance')

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
        if (resp.ok) {
          const data = await resp.json()
          if (mounted) {
            const serverTemplates = Array.isArray(data) ? data : []
            setTemplates(serverTemplates)
            return
          }
        }

        // If backend doesn't expose /api/templates or returned non-200,
        // attempt to load static JSON assets from /templates/index.json
        // which should list available template filenames. Each file is
        // then fetched and parsed as an individual template object.
        try {
          const idxResp = await fetch('/templates/index.json')
          if (!idxResp.ok) throw new Error('no static templates index')
          const index = await idxResp.json()
          if (!Array.isArray(index)) throw new Error('invalid templates index')
          const loads = index.map(fn => fetch(`/templates/${fn}`).then(r => {
            if (!r.ok) throw new Error(`failed to load ${fn}`)
            return r.json()
          }))
          const loaded = await Promise.all(loads)
          if (mounted) {
            setTemplates(loaded)
            return
          }
        } catch (e) {
          // static assets unavailable — fall back to the minimal builtin
          if (mounted) {
            setErr(String(e))
            setTemplates(FALLBACK_TEMPLATES)
          }
        }
      } catch (e) {
        // fallback: provide built-in templates so the UI works
        if (mounted) {
          setErr(String(e))
          setTemplates(FALLBACK_TEMPLATES)
        }
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => { mounted = false }
  }, [open, token])


  const categories = useMemo(() => {
    const set = new Set(['All'])
    for (const t of templates) if (t.category) set.add(t.category)
    return Array.from(set)
  }, [templates])

  const allTags = useMemo(() => {
    const set = new Set()
    for (const t of templates) if (Array.isArray(t.tags)) for (const tg of t.tags) set.add(tg)
    return Array.from(set).sort()
  }, [templates])

  const toggleTag = (tg) => {
    setTagFilters(prev => prev.includes(tg) ? prev.filter(x => x !== tg) : [...prev, tg])
  }

  const matchesQuery = (t) => {
    if (!query) return true
    const q = query.toLowerCase()
    if ((t.title || '').toLowerCase().includes(q)) return true
    if ((t.description || '').toLowerCase().includes(q)) return true
    if ((t.note || '').toLowerCase().includes(q)) return true
    if (Array.isArray(t.tags) && t.tags.join(' ').toLowerCase().includes(q)) return true
    return false
  }

  const filtered = useMemo(() => {
    let list = templates.slice()
    if (category && category !== 'All') list = list.filter(t => t.category === category)
    if (tagFilters.length) list = list.filter(t => Array.isArray(t.tags) && tagFilters.every(f => t.tags.includes(f)))
    list = list.filter(matchesQuery)
    if (sortBy === 'title') list.sort((a,b) => (a.title||'').localeCompare(b.title||''))
    return list
  }, [templates, category, tagFilters, query, sortBy])

  // Do not early-return before all hooks have been declared — hooks must run
  // in the same order on every render. We only skip rendering the modal when
  // `open` is false, but we keep all hooks/derived memos above so React's
  // rules-of-hooks are satisfied.
  if (!open) return null

  const modalContent = (
    <div className="templates-overlay" role="dialog" aria-modal="true">
      <div className="templates-modal" style={{ display: 'flex', gap: 16, padding: 12, maxHeight: '80vh', boxSizing: 'border-box' }}>
        {/* LEFT: fixed-width filter column with its own scroll container */}
        <div style={{ width: 260, borderRight: '1px solid var(--muted)', paddingRight: 12, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>Templates</h3>
            <button onClick={onClose} className="secondary">Close</button>
          </div>

          {/* Scrollable area for filters */}
          <div style={{ marginTop: 12, overflowY: 'auto', paddingRight: 6, flex: 1 }}>
            <div>
              <input placeholder="Search templates" value={query} onChange={e => setQuery(e.target.value)} style={{ width: '100%', padding: '8px' }} />
            </div>

            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>Categories</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {categories.map(cat => (
                  <button key={cat} onClick={() => setCategory(cat)} className={category === cat ? 'active' : 'link'} style={{ textAlign: 'left' }}>{cat}</button>
                ))}
              </div>
            </div>

            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>Tags</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {allTags.map(tg => (
                  <button key={tg} onClick={() => toggleTag(tg)} className={tagFilters.includes(tg) ? 'active' : 'chip'} style={{ fontSize: 12 }}>{tg}</button>
                ))}
              </div>
            </div>

            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>Sort</div>
              <select value={sortBy} onChange={e => setSortBy(e.target.value)} style={{ width: '100%', padding: 6 }}>
                <option value="relevance">Relevance</option>
                <option value="title">Title</option>
              </select>
            </div>
          </div>
        </div>

        {/* RIGHT: main content area with its own scroll container */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ marginBottom: 8 }}>
            {loading && <div>Loading templates…</div>}
            {!loading && err ? <div style={{ color: 'var(--muted)' }}>Using built-in templates ({String(err)})</div> : null}
          </div>

          <div style={{ flex: 1, overflowY: 'auto', paddingLeft: 6 }}>
            <div className="templates-list" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 12 }}>
              {filtered.map(t => (
                <TemplateCard
                  key={t.id}
                  t={t}
                  onApply={onApply}
                  onClose={onClose}
                  setPreview={setPreview}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )

  const previewContent = preview ? (
    <div className="templates-overlay" role="dialog" aria-modal="true" style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <div className="templates-modal" style={{ border: '1px solid var(--muted)', padding: 12, width: '80%', maxWidth: 1000, maxHeight: '80%', overflow: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>{preview.title}</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setPreview(null)} className="secondary">Close</button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 12, marginTop: 12 }}>
          <div>
            <TemplatePreview graph={preview.graph || { nodes: [], edges: [] }} height={420} />
          </div>
          <div style={{ borderLeft: '1px solid var(--muted)', paddingLeft: 12 }}>
            <div style={{ fontSize: 13, color: 'var(--muted)' }}>{preview.description}</div>
            {preview.note ? <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)' }}>{preview.note}</div> : null}
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)' }}>Sample input</div>
              <pre style={{ background: 'var(--panel)', padding: 8, marginTop: 6, maxHeight: 220, overflow: 'auto' }}>{JSON.stringify(preview.sample_input || {}, null, 2)}</pre>
            </div>
          </div>
        </div>

        <div style={{ marginTop: 12, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={() => { onApply && onApply(preview.graph); setPreview(null); onClose && onClose() }}>Use template</button>
          <button onClick={() => {
            try {
              onApply && onApply(preview.graph)
              setTimeout(() => { try { if (window.__editor_runWorkflow) window.__editor_runWorkflow() } catch (e) {} }, 120)
            } finally { setPreview(null); try { onClose && onClose() } catch (e) {} }
          }} className="secondary">Load & Run</button>
        </div>
      </div>
    </div>
  ) : null

  // Portal the entire templates modal to document.body so it lives in the
  // top-level stacking context. This avoids being trapped behind other
  // stacking contexts and ensures the preview portal (which may mount into
  // the modal) paints above page content correctly.
  try {
    if (typeof document !== 'undefined' && document.body) {
      // Portal both the main modal and the preview overlay together into
      // document.body so they share the top-level stacking context and
      // cannot be hidden by ancestor stacking contexts. We wrap them in a
      // single container to ensure ordering: previewContent should render
      // after modalContent so it paints above.
      return createPortal(
        <>
          {modalContent}
          {previewContent}
        </>,
        document.body
      )
    }
  } catch (e) {
    // fallback to inline render if portal fails for any environment (SSR/test)
  }

  // If portal cannot be used (tests/SSR), render inline. Ensure preview is
  // rendered after the modal so it appears above when possible.
  return (
    <>
      {modalContent}
      {previewContent}
    </>
  )
}
