import React from 'react'

export default function SlackNode({ register, providers, selectedNode }) {
  const cfg = (selectedNode.data && selectedNode.data.config) || {}
  return (
    <div>
      <label>Channel</label>
      <input {...register('channel')} defaultValue={cfg.channel || ''} style={{ width: '100%', marginBottom: 8 }} />
      <label>Text</label>
      <textarea {...register('text')} defaultValue={cfg.text || ''} style={{ width: '100%', height: 120 }} />
      <label>Provider</label>
      <select {...register('provider_id')} defaultValue={cfg.provider_id || ''} style={{ width: '100%', marginTop: 8 }}>
        <option value=''>-- Select provider --</option>
        {providers.map(p => <option key={p.id} value={p.id}>{p.type} (id:{p.id})</option>)}
      </select>
    </div>
  )
}
