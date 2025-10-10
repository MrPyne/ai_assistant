import React from 'react'

export default function SecretRow({s, onDelete}){
  return (
    <div style={{ padding: 6, borderBottom: '1px solid #eee' }}>
      <div><strong>{s.name}</strong></div>
      <div className="muted">id: {s.id} created_by: {s.created_by} <button onClick={() => onDelete(s.id)} style={{ marginLeft: 8 }}>Delete</button></div>
    </div>
  )
}
