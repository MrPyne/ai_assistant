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
        // fallback: provide a set of built-in example templates so the UI works
        if (mounted) {
          setErr(String(e))
          setTemplates([
            {
              id: 'starter-1',
              title: 'HTTP -> LLM',
              description: 'Simple pipeline: HTTP request -> LLM processing',
              note: 'Basic starter: HTTP trigger -> HTTP request -> LLM. Use this to explore saving and running workflows.',
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
              note: 'Runs serially. max_chunks is UI-only; backend ignores it. Dotted input_path resolves nested fields; non-list becomes single chunk.',
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
              note: 'Runs chunks in parallel up to `concurrency` workers. Errors may stop remaining chunks depending on fail_behavior.',
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
                {t.note ? <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>{t.note}</div> : null}
                <div style={{ marginTop: 8 }}>
                  <TemplatePreview graph={t.graph || { nodes: [], edges: [] }} height={140} />
                </div>
                <div className="template-actions">
                  <button onClick={() => { onApply && onApply(t.graph); onClose && onClose() }}>Use template</button>
                  {/* Load & Run: apply template then trigger editor run helper if available */}
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
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
