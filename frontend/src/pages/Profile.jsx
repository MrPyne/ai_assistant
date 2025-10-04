import React, { useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

export default function Profile(){
  const { token } = useAuth()
  const [profile, setProfile] = useState(null)

  useEffect(() => {
    if (!token) return
    const fetchProfile = async () => {
      try {
        const resp = await fetch('/api/me', { headers: { 'Authorization': `Bearer ${token}` } })
        if (resp.ok) {
          const data = await resp.json()
          setProfile(data)
        }
      } catch (err) {}
    }
    fetchProfile()
  }, [token])

  return (
    <div style={{ padding: 20 }}>
      <h3>Profile</h3>
      {profile ? (
        <div>
          <div><strong>Email:</strong> {profile.email}</div>
          <div style={{ marginTop: 8 }}><strong>Workspace:</strong> {profile.workspace || 'default'}</div>
        </div>
      ) : (
        <div style={{ color: '#666' }}>No profile loaded</div>
      )}
    </div>
  )
}
