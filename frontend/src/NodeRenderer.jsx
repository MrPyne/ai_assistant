import React from 'react'

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

export default function NodeRenderer({ data }) {
  const label = data && data.label ? data.label : ''
  const config = data && data.config ? data.config : {}

  let type = 'generic'
  if (label && label.toLowerCase().includes('webhook')) type = 'webhook'
  else if (label && (label.toLowerCase().includes('http') || label.toLowerCase().includes('request'))) type = 'http'
  else if (label && (label.toLowerCase().includes('llm') || label.toLowerCase().includes('ai') || label.toLowerCase().includes('model'))) type = 'llm'

  return (
    <div className="node-card" tabIndex={0}>
      <div className="node-header">
        <span className={`node-icon node-icon-${type}`} aria-hidden>
          <Icon type={type} />
        </span>
        <div className="label">{label}</div>
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>{Object.keys(config).length ? JSON.stringify(config) : ''}</div>
    </div>
  )
}
