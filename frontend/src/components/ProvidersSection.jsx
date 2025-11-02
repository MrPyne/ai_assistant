import React, { useEffect, useState } from 'react'
import ProviderForm from './ProviderForm'
import ProviderEditModal from './ProviderEditModal'

export default function ProvidersSection({ providers = [], token, loadProviders, loadSecrets, testProvider }) {
  const [selectedProviderId, setSelectedProviderId] = useState(providers && providers.length ? String(providers[0].id) : '')
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState(null)

  useEffect(() => {
    if (providers && providers.length && !providers.find(p => String(p.id) === selectedProviderId)) {
      setSelectedProviderId(String(providers[0].id))
    }
  }, [providers])

  return (
    <div>
      <ProviderForm
        token={token}
        secrets={[]}
        loadProviders={async () => { try { if (token) await loadProviders(); else await loadProviders() } catch (e) {} }}
        loadSecrets={loadSecrets}
        onCreated={(p) => { try { loadProviders(); loadSecrets && loadSecrets(); alert('Provider created') } catch (e) {} }}
      />

      <div style={{ marginBottom: 8 }}>
        <label style={{ display: 'block', marginBottom: 4 }}>Existing providers</label>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <select value={selectedProviderId} onChange={(e) => setSelectedProviderId(e.target.value)} style={{ flex: 1 }}>
            {providers.length === 0 ? <option value=''>No providers</option> : providers.map(p => <option key={p.id} value={p.id}>{p.type} (id:{p.id})</option>)}
          </select>
          <button onClick={() => { const p = providers.find(x => String(x.id) === selectedProviderId); if (p) alert(`Provider: ${p.type} (id:${p.id})`)}} className="secondary">Info</button>
          <button onClick={() => { if (!selectedProviderId) return alert('Select a provider'); testProvider && testProvider(Number(selectedProviderId)) }} className="secondary">Test</button>
          <button onClick={() => {
            if (!selectedProviderId) return alert('Select a provider')
            const p = providers.find(x => String(x.id) === selectedProviderId)
            if (!p) return alert('Provider not found')
            setEditingProvider(p)
            setEditModalOpen(true)
          }} className="secondary">Edit</button>
        </div>
      </div>

      {editModalOpen ? (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 'var(--z-templates-overlay, 2000)' }}>
          <div style={{ background: 'var(--bg)', padding: 16, borderRadius: 8, width: '90%', maxWidth: 720, zIndex: 'var(--z-templates-modal, 2001)' }}>
            <h3>Edit Provider</h3>
            {editingProvider ? (
              <ProviderEditModal provider={editingProvider} token={token} onClose={() => { setEditModalOpen(false); setEditingProvider(null); loadProviders && loadProviders(); loadSecrets && loadSecrets() }} loadSecrets={loadSecrets} />
            ) : (
              <div>No provider selected</div>
            )}
            <div style={{ marginTop: 8 }}>
              <button onClick={() => setEditModalOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
