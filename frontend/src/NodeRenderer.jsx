import './styles/NodeRenderer.css'
import React from 'react'
import { Handle, Position } from 'react-flow-renderer'
import SlackNode from './nodes/SlackNode'
import EmailNode from './nodes/EmailNode'
import { useEditorDispatch } from './state/EditorContext'
import Icon from './NodeIcon'
import { inferKindFromLabel, resultPreviewFromRuntime, truncated as _truncated } from './nodeHelpers'

export default function NodeRenderer(props) {
  // Be defensive: react-flow may pass different shapes depending on version.
  const { data = {}, id, type: nodeType } = props || {}
  const config = data && data.config && typeof data.config === 'object' ? data.config : {}
  const isInvalid = data && (data.validation_error || data.__validation_error)

  const { rawLabel, label, kind, isIf, isSwitch } = inferKindFromLabel(data && data.label, nodeType, id)

  const editorDispatch = useEditorDispatch()

  // runtime information (populated by SSE / run replay). Do not mutate config.
  const runtime = data && data.runtime ? data.runtime : null
  const status = runtime && runtime.status ? String(runtime.status).toLowerCase() : null
  const progress = runtime && (typeof runtime.progress === 'number' || typeof runtime.progress === 'string') ? Number(runtime.progress) : null
  const resultPreview = resultPreviewFromRuntime(runtime)

  const truncated = (s, n = 100) => _truncated(s, n)

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
              <span className="runtime-icon" aria-hidden style={{ color: 'var(--muted)', fontSize: 12 }}>•</span>
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
          {_truncated(resultPreview, 120)}
        </div>
      ) : null}

      {/* Render specialized small inspector fragments for certain node types */}
      <div style={{ padding: '6px 10px', width: '100%' }}>
        {kind === 'slack' && <div style={{ fontSize: 12, color: 'var(--muted)' }}>Slack target - {config.channel || '#channel'}</div>}
        {kind === 'email' && <div style={{ fontSize: 12, color: 'var(--muted)' }}>Email - {config.to || 'recipient'}</div>}
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
