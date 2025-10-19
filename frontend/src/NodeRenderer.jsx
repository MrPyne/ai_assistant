import './styles/NodeRenderer.css'
import React from 'react'
import { Handle, Position } from 'react-flow-renderer'
import SlackNode from './nodes/SlackNode'
import EmailNode from './nodes/EmailNode'
import { useEditorDispatch } from './state/EditorContext'

function Icon({ type, size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  if (type === 'webhook') {
    return (
      <svg {...common} stroke="currentColor">
        <path d="M12 2v6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M19 7l-7 7-7-7" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (type === 'http') {
    return (
      <svg {...common} stroke="currentColor">
        <path d="M3 12h18" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M12 3v18" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (type === 'llm') {
    return (
      <svg {...common} stroke="currentColor">
        <path d="M12 3C9.238 3 7 5.238 7 8c0 1.657.895 3.105 2.29 3.932L9 17l3.245-1.073A5.002 5.002 0 0017 8c0-2.762-2.238-5-5-5z" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  // default / generic
  return (
    <svg {...common} stroke="currentColor">
      <circle cx="12" cy="12" r="9" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// extra icons
Icon.Email = function EmailIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <rect x="3" y="5" width="18" height="14" rx="2" strokeWidth="1.2" />
      <path d="M3 7l9 6 9-6" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

Icon.Cron = function CronIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <circle cx="12" cy="12" r="9" strokeWidth="1.2" />
      <path d="M12 7v5l3 3" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

Icon.Slack = function SlackIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <path d="M14 3h2a2 2 0 012 2v2" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M10 21H8a2 2 0 01-2-2v-2" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M21 14v2a2 2 0 01-2 2h-2" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M3 10V8a2 2 0 012-2h2" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

Icon.DB = function DbIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <ellipse cx="12" cy="6" rx="8" ry="3" strokeWidth="1.2" />
      <path d="M4 6v6c0 1.657 3.582 3 8 3s8-1.343 8-3V6" strokeWidth="1.2" />
    </svg>
  )
}

Icon.S3 = function S3Icon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <rect x="3" y="7" width="18" height="10" rx="2" strokeWidth="1.2" />
      <path d="M7 11h10" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

Icon.Transform = function TransformIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <path d="M4 7h6l2 3 6-3" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 17h16" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

Icon.Wait = function WaitIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <path d="M12 7v5l3 3" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="9" strokeWidth="1.2" />
    </svg>
  )
}

export default function NodeRenderer(props) {
  // Be defensive: react-flow may pass different shapes depending on version.
  const { data = {}, id, type: nodeType } = props || {}
  const config = data && data.config && typeof data.config === 'object' ? data.config : {}
  const isInvalid = data && (data.validation_error || data.__validation_error)

  // Compute a human-friendly label with several fallbacks so nodes never render empty
  const rawLabel = (typeof data.label === 'string' && data.label.trim()) ? data.label.trim() : null
  const label = rawLabel || (nodeType === 'input' ? 'Webhook Trigger' : null) || nodeType || id || 'Node'

  // infer icon type from label OR node type
  let kind = 'generic'
  const l = (label || '').toLowerCase()
  if (l.includes('webhook')) kind = 'webhook'
  else if (l.includes('http') || l.includes('request')) kind = 'http'
  else if (l.includes('llm') || l.includes('ai') || l.includes('model')) kind = 'llm'

  // additional kinds
  else if (l.includes('email') || l.includes('send email') || l.includes('send-email')) kind = 'email'
  else if (l.includes('cron') || l.includes('timer')) kind = 'cron'
  else if (l.includes('slack')) kind = 'slack'
  else if (l.includes('db') || l.includes('query')) kind = 'db'
  else if (l.includes('s3') || l.includes('upload')) kind = 's3'
  else if (l.includes('transform') || l.includes('jinja') || l.includes('template')) kind = 'transform'
  else if (l.includes('wait') || l.includes('delay')) kind = 'wait'

  const isIf = l === 'if' || l === 'condition'
  const isSwitch = l === 'switch'
  const editorDispatch = useEditorDispatch()

  // runtime information (populated by SSE / run replay). Do not mutate config.
  const runtime = data && data.runtime ? data.runtime : null
  const status = runtime && runtime.status ? String(runtime.status).toLowerCase() : null
  const progress = runtime && (typeof runtime.progress === 'number' || typeof runtime.progress === 'string') ? Number(runtime.progress) : null
  const resultPreview = (() => {
    if (!runtime) return null
    if (runtime.result) {
      if (typeof runtime.result === 'string') return runtime.result
      try { return JSON.stringify(runtime.result) } catch (e) { return String(runtime.result) }
    }
    if (runtime.error) return runtime.error.message || (typeof runtime.error === 'string' ? runtime.error : JSON.stringify(runtime.error))
    if (runtime.message) return runtime.message
    return null
  })()

  const truncated = (s, n = 100) => (typeof s === 'string' && s.length > n) ? s.slice(0, n - 1) + '...' : s

  const openInspector = (e) => {
    e && e.stopPropagation()
    try {
      editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: id })
      editorDispatch({ type: 'SET_RIGHT_PANEL_OPEN', payload: true })
      editorDispatch({ type: 'SET_ACTIVE_RIGHT_TAB', payload: 'inspector' })
    } catch (err) {
      // ignore if editor context not available
    }
  }
  const isRunning = status === 'running'

  // Build the style object but avoid assigning zIndex when this node is
  // being rendered inside a preview (templates / TemplatePreview). The
  // TemplatePreview sets data.__preview = true on nodes it renders so we
  // can detect that and not include a z-index which would otherwise compete
  // with dialog z-index rules.
  const baseStyle = isInvalid
    ? { border: '2px solid #ff4d4f', boxShadow: '0 2px 8px rgba(255,77,79,0.15)', opacity: 1, display: 'flex', backgroundColor: 'rgba(255,255,255,0.08)', color: '#e6eef6', pointerEvents: 'auto' }
    : { opacity: 1, display: 'flex', backgroundColor: 'rgba(255,255,255,0.08)', color: '#e6eef6', pointerEvents: 'auto' }

  // If not a preview, include the canvas z-index so nodes sit above other
  // canvas content but beneath dialogs. For previews we deliberately omit
  // zIndex so previews never outrank modals.
  const isPreview = data && data.__preview
  const style = isPreview ? baseStyle : { ...baseStyle, zIndex: 'var(--z-canvas, 1500)' }

  return (
    <div
      className={`node-card${isRunning ? ' node-running' : ''}`}
      tabIndex={0}
      style={style}
      data-node-id={id}
    >
      {/* Target / input handle on the left */}
      <Handle
        type="target"
        id="in"
        position={Position.Left}
        className="rf-handle-left"
      />

      <div className="node-header">
        <span className={`node-icon node-icon-${kind}`} aria-hidden>
          {kind === 'email' ? <Icon.Email /> : kind === 'cron' ? <Icon.Cron /> : kind === 'slack' ? <Icon.Slack /> : kind === 'db' ? <Icon.DB /> : kind === 's3' ? <Icon.S3 /> : kind === 'transform' ? <Icon.Transform /> : kind === 'wait' ? <Icon.Wait /> : <Icon type={kind} />}
        </span>
        <div className="label">{label}</div>
        {/* runtime badge: lightweight indicator and quick-inspect affordance */}
        {runtime && (
          <div
            className={`node-runtime-badge runtime-${status || 'idle'}`}
            onClick={openInspector}
            title={runtime && runtime.status ? `${runtime.status}${progress ? ` - ${progress}%` : ''}` : 'Runtime'}
            style={{ marginLeft: '8px', display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
          >
            {status === 'running' ? (
              <span className="runtime-spinner" aria-hidden style={{ width: 12, height: 12, borderRadius: 6, border: '2px solid rgba(0,0,0,0.1)', borderTopColor: '#5fb0ff', boxSizing: 'border-box', animation: 'spin 1s linear infinite' }} />
            ) : status === 'success' ? (
              <span className="runtime-icon" aria-hidden style={{ color: '#66ffa6', fontSize: 12, fontWeight: 700 }}>OK</span>
            ) : status === 'failed' ? (
              <span className="runtime-icon" aria-hidden style={{ color: '#ff6b6b', fontSize: 12, fontWeight: 700 }}>ERR</span>
            ) : (
              <span className="runtime-icon" aria-hidden style={{ color: 'var(--muted)', fontSize: 12 }}>â€¢</span>
            )}
            {typeof progress === 'number' && !Number.isNaN(progress) && (
              <span className="runtime-pct" style={{ fontSize: 11, color: 'var(--muted)' }}>{Math.round(progress)}%</span>
            )}
          </div>
        )}
      </div>

      {/* show a minimal config preview so node isn't an empty box */}
      <div className="node-meta">{Object.keys(config || {}).length ? JSON.stringify(config) : ''}</div>

      {/* small footer to show truncated result / error summary (if present) */}
      {resultPreview ? (
        <div className="node-footer" onClick={openInspector} title={resultPreview} style={{ marginTop: 6, fontSize: 12, color: 'var(--muted)', cursor: 'pointer' }}>
          {truncated(resultPreview, 120)}
        </div>
      ) : null}

      {/* Render specialized small inspector fragments for certain node types */}
      <div style={{ padding: '6px 10px', width: '100%' }}>
        {kind === 'slack' && <div style={{ fontSize: 12, color: 'var(--muted)' }}>Slack target · {config.channel || '#channel'}</div>}
        {kind === 'email' && <div style={{ fontSize: 12, color: 'var(--muted)' }}>Email · {config.to || 'recipient'}</div>}
      </div>

      {/* Outputs */}
      {/* Execution overlay: visual loading indicator when node is running */}
      {isRunning && (
        <div className="node-running-overlay" aria-hidden>
          <div className="node-running-spinner" />
        </div>
      )}

      {isIf ? (
        <>
          <Handle
            type="source"
            id="true"
            position={Position.Right}
            className="rf-handle-true"
          />
          <div className="handle-label handle-label-true">T</div>
          <Handle
            type="source"
            id="false"
            position={Position.Right}
            className="rf-handle-false"
          />
          <div className="handle-label handle-label-false">F</div>
        </>
      ) : isSwitch ? (
        <Handle
          type="source"
          id="out"
          position={Position.Right}
          className="rf-handle-right"
        />
      ) : (
        <Handle type="source" id="out" position={Position.Right} className="rf-handle-right" />
      )}
    </div>
  )
}
