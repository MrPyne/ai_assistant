import React from 'react'

export default function EmailNode({ register, providers, selectedNode }) {
  const cfg = (selectedNode.data && selectedNode.data.config) || {}
  return (
    <div>
      <label>To</label>
      <input {...register('to')} defaultValue={cfg.to || ''} style={{ width: '100%', marginBottom: 8 }} />
      <label>From</label>
      <input {...register('from')} defaultValue={cfg.from || ''} style={{ width: '100%', marginBottom: 8 }} />
      <label>Subject</label>
      <input {...register('subject')} defaultValue={cfg.subject || ''} style={{ width: '100%', marginBottom: 8 }} />
      <label>Body</label>
      <textarea {...register('body')} defaultValue={cfg.body || ''} style={{ width: '100%', height: 120 }} />
      <label>Provider</label>
      <select {...register('provider_id')} defaultValue={cfg.provider_id || ''} style={{ width: '100%', marginTop: 8 }}>
        <option value=''>-- Select provider --</option>
        {providers.map(p => <option key={p.id} value={p.id}>{p.type} (id:{p.id})</option>)}
      </select>
    </div>
  )
}
