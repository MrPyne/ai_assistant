import React from 'react'
import { Handle, Position } from 'react-flow-renderer'

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

  const isIf = l === 'if' || l === 'condition'
  const isSwitch = l === 'switch'

  return (
    <div
      className="node-card"
      tabIndex={0}
      style={isInvalid ? { border: '2px solid #ff4d4f', boxShadow: '0 2px 8px rgba(255,77,79,0.15)' } : {}}
      data-node-id={id}
    >
      {/* Target / input handle on the left */}
      <Handle type="target" id="in" position={Position.Left} className="rf-handle-left" />

      <div className="node-header">
        <span className={`node-icon node-icon-${kind}`} aria-hidden>
          <Icon type={kind} />
        </span>
        <div className="label">{label}</div>
      </div>

      {/* show a minimal config preview so node isn't an empty box */}
      <div className="node-meta">{Object.keys(config || {}).length ? JSON.stringify(config) : ''}</div>

      {/* Outputs */}
      {isIf ? (
        <>
          <Handle type="source" id="true" position={Position.Right} style={{ top: 18 }} className="rf-handle-true" />
          <div className="handle-label handle-label-true">T</div>
          <Handle type="source" id="false" position={Position.Right} style={{ bottom: 18 }} className="rf-handle-false" />
          <div className="handle-label handle-label-false">F</div>
        </>
      ) : isSwitch ? (
        <Handle type="source" id="out" position={Position.Right} className="rf-handle-right" />
      ) : (
        <Handle type="source" id="out" position={Position.Right} className="rf-handle-right" />
      )}
    </div>
  )
}
