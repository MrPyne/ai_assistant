import React from 'react'

export default function NodeRenderer({ data }) {
  const label = data && data.label ? data.label : ''
  const config = data && data.config ? data.config : {}

  return (
    <div style={{ padding: 8, border: '1px solid #ddd', borderRadius: 6, background: '#fff', minWidth: 160 }}>
      <div style={{ fontWeight: '600', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 12, color: '#666' }}>{Object.keys(config).length ? JSON.stringify(config) : ''}</div>
    </div>
  )
}
