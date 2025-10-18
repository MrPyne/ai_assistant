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

// Built-in example templates. These are always available and will be
// merged with any templates returned from the /api/templates endpoint.
const BUILTIN_TEMPLATES = [
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
  },

  {
    id: 'split-basic',
    title: 'SplitInBatches — basic',
    description: 'Split a list into chunks and process each chunk serially with a simple transform',
    category: 'Batch processing',
    tags: ['split', 'batch', 'serial'],
    note: 'Runs serially. max_chunks is UI-only; backend ignores it. Dotted input_path resolves nested fields; non-list becomes single chunk.',
    sample_input: { input: { items: ['alpha','bravo','charlie','delta','echo','foxtrot'] } },
    graph: {
      nodes: [
        { id: 's1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Trigger', config: {} } },
        { id: 's2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'SplitInBatches', config: { input_path: 'input.items', batch_size: 5, mode: 'serial', concurrency: 1, fail_behavior: 'stop_on_error' } } },
        { id: 's3', type: 'action', position: { x: 440, y: 0 }, data: { label: 'Transform (per-chunk)', config: { language: 'jinja', template: 'Processed: {{ item }}' } } },
      ],
      edges: [ { id: 'se1', source: 's1', target: 's2' }, { id: 'se2', source: 's2', target: 's3' } ]
    }
  },

  {
    id: 'split-parallel',
    title: 'SplitInBatches — parallel',
    description: 'Run chunk processing in parallel (concurrency controls number of workers)',
    category: 'Batch processing',
    tags: ['split', 'batch', 'parallel'],
    note: 'Runs chunks in parallel up to `concurrency` workers. Errors may stop remaining chunks depending on fail_behavior.',
    sample_input: { payload: { records: Array.from({ length: 24 }, (_, i) => `record-${i+1}`) } },
    graph: {
      nodes: [
        { id: 'p1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Trigger', config: {} } },
        { id: 'p2', type: 'action', position: { x: 220, y: -30 }, data: { label: 'SplitInBatches', config: { input_path: 'payload.records', batch_size: 10, mode: 'parallel', concurrency: 3, fail_behavior: 'stop_on_error' } } },
        { id: 'p3', type: 'llm', position: { x: 440, y: -30 }, data: { label: 'LLM (per-chunk)', config: { model: 'gpt', prompt: 'Summarize: {{ item }}' } } },
      ],
      edges: [ { id: 'pe1', source: 'p1', target: 'p2' }, { id: 'pe2', source: 'p2', target: 'p3' } ]
    }
  },

  {
    id: 'split-fail-continue',
    title: 'SplitInBatches — continue on error',
    description: 'Demonstrates fail_behavior=continue_on_error: errors in some chunks do not stop the whole run',
    category: 'Batch processing',
    tags: ['split', 'retry', 'robustness'],
    note: 'With continue_on_error the runner collects errors and proceeds; results include both successes and error entries.',
    graph: {
      nodes: [
        { id: 'f1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Trigger', config: {} } },
        { id: 'f2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'SplitInBatches', config: { input_path: 'items', batch_size: 3, mode: 'serial', concurrency: 2, fail_behavior: 'continue_on_error' } } },
        { id: 'f3', type: 'action', position: { x: 440, y: 0 }, data: { label: 'Unstable Transform', config: { language: 'jinja', template: "{{ item }} | maybe-fail" } } },
      ],
      edges: [ { id: 'fe1', source: 'f1', target: 'f2' }, { id: 'fe2', source: 'f2', target: 'f3' } ]
    }
  },

  {
    id: 'split-non-list',
    title: 'Non-list input demo',
    description: 'If the input path points to a single value the node processes it as one chunk',
    category: 'Batch processing',
    tags: ['split', 'edge-case'],
    note: 'When the resolved value is not a list it will be treated as a single chunk (sequence length = 1).',
    graph: {
      nodes: [
        { id: 'nl1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Trigger', config: {} } },
        { id: 'nl2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'SplitInBatches', config: { input_path: 'input', batch_size: 2, mode: 'serial', concurrency: 1, fail_behavior: 'stop_on_error' } } },
        { id: 'nl3', type: 'action', position: { x: 440, y: 0 }, data: { label: 'Transform', config: { language: 'jinja', template: '{{ item }}' } } },
      ],
      edges: [ { id: 'nle1', source: 'nl1', target: 'nl2' }, { id: 'nle2', source: 'nl2', target: 'nl3' } ]
    }
  },

  {
    id: 'split-max-chunks-ui',
    title: 'Max chunks (UI-only)',
    description: "Set max_chunks in the UI to limit how many chunks the editor creates — note: backend currently ignores this field",
    category: 'Batch processing',
    tags: ['ui', 'split'],
    note: 'max_chunks is a UI convenience only; the backend currently ignores this setting.',
    graph: {
      nodes: [
        { id: 'm1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Trigger', config: {} } },
        { id: 'm2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'SplitInBatches', config: { input_path: 'events', batch_size: 2, mode: 'serial', concurrency: 2, fail_behavior: 'stop_on_error', max_chunks: '2' } } },
        { id: 'm3', type: 'action', position: { x: 440, y: 0 }, data: { label: 'Transform', config: { language: 'jinja', template: '{{ item }}' } } },
      ],
      edges: [ { id: 'me1', source: 'm1', target: 'm2' }, { id: 'me2', source: 'm2', target: 'm3' } ]
    }
  },

  {
    id: 'split-nested-path',
    title: 'Nested input_path example',
    description: "Target a nested array like payload.records.list and process each chunk",
    category: 'Batch processing',
    tags: ['split', 'paths', 'nested'],
    note: 'Use dotted paths to target nested arrays. If the path is missing the runner treats it as empty list.',
    graph: {
      nodes: [
        { id: 'np1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Trigger', config: {} } },
        { id: 'np2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'SplitInBatches', config: { input_path: 'payload.records.list', batch_size: 4, mode: 'serial', concurrency: 1, fail_behavior: 'stop_on_error' } } },
        { id: 'np3', type: 'llm', position: { x: 440, y: 0 }, data: { label: 'LLM (per-chunk)', config: { model: 'gpt', prompt: 'Process: {{ item }}' } } },
      ],
      edges: [ { id: 'npe1', source: 'np1', target: 'np2' }, { id: 'npe2', source: 'np2', target: 'np3' } ]
    }
  },

  {
    id: 'split-combined-downstream',
    title: 'Split + downstream aggregation',
    description: 'Split into chunks, process in parallel, then downstream nodes aggregate or collect results',
    category: 'Batch processing',
    tags: ['split', 'aggregation', 'parallel'],
    note: 'Downstream nodes receive synthetic sub-run ids for each chunk. Aggregation must handle multiple sub-run outputs.',
    graph: {
      nodes: [
        { id: 'c1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Trigger', config: {} } },
        { id: 'c2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'SplitInBatches', config: { input_path: 'items', batch_size: 20, mode: 'parallel', concurrency: 4, fail_behavior: 'continue_on_error' } } },
        { id: 'c3', type: 'llm', position: { x: 440, y: -30 }, data: { label: 'LLM (per-chunk)', config: { model: 'gpt', prompt: 'Analyze: {{ item }}' } } },
        { id: 'c4', type: 'action', position: { x: 660, y: 0 }, data: { label: 'Combine Results', config: { language: 'jinja', template: "Combined {{ results|length }} items" } } },
      ],
      edges: [ { id: 'ce1', source: 'c1', target: 'c2' }, { id: 'ce2', source: 'c2', target: 'c3' }, { id: 'ce3', source: 'c3', target: 'c4' } ]
    }
  },

  {
    id: 'webhook-to-db',
    title: 'Webhook -> Transform -> DB upsert',
    description: 'Ingest webhook payload, transform and upsert into a database',
    category: 'Integrations',
    tags: ['webhook', 'db', 'etl'],
    note: 'Common pattern for accepting external events and persisting normalized records.',
    sample_input: { event: { id: 'evt_123', payload: { user: { id: 42, name: 'Alice' } } } },
    graph: {
      nodes: [
        { id: 'w1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Webhook Trigger', config: {} } },
        { id: 'w2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'Transform (normalize)', config: { language: 'jinja', template: "{{ event.payload.user | tojson }}" } } },
        { id: 'w3', type: 'action', position: { x: 440, y: 0 }, data: { label: 'DB Upsert', config: { query: 'UPSERT INTO users ...' } } },
      ],
      edges: [ { id: 'we1', source: 'w1', target: 'w2' }, { id: 'we2', source: 'w2', target: 'w3' } ]
    }
  },

  {
    id: 'scheduled-report-slack',
    title: 'Cron -> DB Query -> LLM Summary -> Slack',
    description: 'Run a scheduled report: query DB, summarize with LLM, send to Slack',
    category: 'Automation',
    tags: ['cron', 'report', 'slack', 'llm'],
    note: 'Useful for nightly summaries or digest notifications.',
    sample_input: { run: { period: 'daily' } },
    graph: {
      nodes: [
        { id: 'r1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Cron Trigger', config: { schedule: '0 6 * * *' } } },
        { id: 'r2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'DB Query', config: { sql: 'SELECT count(*) as cnt, avg(duration) as avg_d FROM runs WHERE ts > now() - interval 1 day' } } },
        { id: 'r3', type: 'llm', position: { x: 440, y: 0 }, data: { label: 'LLM (summarize)', config: { model: 'gpt', prompt: 'Create a short report from: {{ rows }}' } } },
        { id: 'r4', type: 'action', position: { x: 660, y: 0 }, data: { label: 'Slack - Post', config: { channel: '#alerts', text: 'Report: {{ summary }}' } } },
      ],
      edges: [ { id: 're1', source: 'r1', target: 'r2' }, { id: 're2', source: 'r2', target: 'r3' }, { id: 're3', source: 'r3', target: 'r4' } ]
    }
  },

  {
    id: 's3-llm-extract',
    title: 'S3 Ingest -> LLM Extract -> DB',
    description: 'Process files from S3: extract text with LLM and store results',
    category: 'Data pipelines',
    tags: ['s3', 'llm', 'extract', 'db'],
    note: 'Ideal for document ingestion workflows (OCR/LLM extraction)',
    sample_input: { s3: { bucket: 'uploads', key: 'invoices/2025/01/01.pdf' } },
    graph: {
      nodes: [
        { id: 's31', type: 'input', position: { x: 0, y: 0 }, data: { label: 'S3 Event', config: {} } },
        { id: 's32', type: 'action', position: { x: 220, y: 0 }, data: { label: 'Download from S3', config: { bucket: '{{ s3.bucket }}', key: '{{ s3.key }}' } } },
        { id: 's33', type: 'llm', position: { x: 440, y: 0 }, data: { label: 'LLM - Extract Text', config: { model: 'gpt', prompt: 'Extract structured data: {{ file_text }}' } } },
        { id: 's34', type: 'action', position: { x: 660, y: 0 }, data: { label: 'DB Insert', config: { table: 'documents', fields: ['title','summary','entities'] } } },
      ],
      edges: [ { id: 's3e1', source: 's31', target: 's32' }, { id: 's3e2', source: 's32', target: 's33' }, { id: 's3e3', source: 's33', target: 's34' } ]
    }
  },

  {
    id: 'http-parallel-enrich-aggregate',
    title: 'HTTP -> Parallel Enrich -> Aggregate',
    description: 'Call external API for items, enrich each in parallel with LLM, then combine',
    category: 'Data pipelines',
    tags: ['http', 'llm', 'parallel', 'aggregation'],
    note: 'Demonstrates parallel SplitInBatches followed by an aggregation step.',
    sample_input: { items: ['item1','item2','item3','item4'] },
    graph: {
      nodes: [
        { id: 'h1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Trigger', config: {} } },
        { id: 'h2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'SplitInBatches', config: { input_path: 'items', batch_size: 10, mode: 'parallel', concurrency: 4 } } },
        { id: 'h3', type: 'llm', position: { x: 440, y: -20 }, data: { label: 'LLM Enrich', config: { model: 'gpt', prompt: 'Enrich: {{ item }}' } } },
        { id: 'h4', type: 'action', position: { x: 660, y: 0 }, data: { label: 'Aggregate Results', config: { language: 'jinja', template: 'Aggregated {{ results|length }} items' } } },
      ],
      edges: [ { id: 'he1', source: 'h1', target: 'h2' }, { id: 'he2', source: 'h2', target: 'h3' }, { id: 'he3', source: 'h3', target: 'h4' } ]
    }
  },

  {
    id: 'webhook-routing-branch',
    title: 'Webhook -> If routing -> Email / Slack',
    description: 'Route incoming webhooks to channels based on payload conditions',
    category: 'Notifications',
    tags: ['webhook', 'routing', 'email', 'slack', 'condition'],
    note: 'Shows conditional routing using an If/Condition node.',
    sample_input: { event: { type: 'signup', user: { email: 'a@b.com' } } },
    graph: {
      nodes: [
        { id: 'br1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Webhook Trigger', config: {} } },
        { id: 'br2', type: 'action', position: { x: 220, y: 0 }, data: { label: 'If', config: { condition: "event.type == 'signup'" } } },
        { id: 'br3', type: 'action', position: { x: 440, y: -40 }, data: { label: 'Send Email', config: { to: "{{ event.user.email }}", subject: 'Welcome' } } },
        { id: 'br4', type: 'action', position: { x: 440, y: 40 }, data: { label: 'Slack - Post', config: { channel: '#events', text: 'Event: {{ event.type }}' } } },
      ],
      edges: [ { id: 'bre1', source: 'br1', target: 'br2' }, { id: 'bre2', source: 'br2', target: 'br3' }, { id: 'bre3', source: 'br2', target: 'br4' } ]
    }
  },

  {
    id: 'http-retry-backoff',
    title: 'HTTP call with retry/backoff',
    description: 'Attempt an HTTP request, retry with delay on transient errors',
    category: 'Reliability',
    tags: ['http', 'retry', 'backoff'],
    note: 'Pattern for robust external calls with retry and wait/delay nodes.',
    sample_input: { url: 'https://api.example.com/slow' },
    graph: {
      nodes: [
        { id: 'rt1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Trigger', config: {} } },
        { id: 'rt2', type: 'http', position: { x: 220, y: 0 }, data: { label: 'HTTP Request', config: { method: 'POST', url: '{{ url }}' } } },
        { id: 'rt3', type: 'action', position: { x: 440, y: 0 }, data: { label: 'If (error?)', config: { condition: 'response.status >= 500' } } },
        { id: 'rt4', type: 'action', position: { x: 660, y: -20 }, data: { label: 'Wait 5s', config: { seconds: 5 } } },
        { id: 'rt5', type: 'action', position: { x: 880, y: 0 }, data: { label: 'Retry HTTP', config: { attempts: 3 } } },
      ],
      edges: [ { id: 'rte1', source: 'rt1', target: 'rt2' }, { id: 'rte2', source: 'rt2', target: 'rt3' }, { id: 'rte3', source: 'rt3', target: 'rt4' }, { id: 'rte4', source: 'rt4', target: 'rt5' } ]
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
        if (!resp.ok) {
          // no backend endpoint or non-200 — fall back to builtin templates
          throw new Error(`no remote templates: ${resp.status}`)
        }
        const data = await resp.json()
        if (mounted) {
          const serverTemplates = Array.isArray(data) ? data : []
          // Merge server templates with built-ins, prefer server-provided template when ids clash
          const merged = [...serverTemplates]
          for (const bt of BUILTIN_TEMPLATES) {
            if (!serverTemplates.some(st => st.id === bt.id)) merged.push(bt)
          }
          setTemplates(merged)
        }
      } catch (e) {
        // fallback: provide built-in templates so the UI works
        if (mounted) {
          setErr(String(e))
          setTemplates(BUILTIN_TEMPLATES)
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
