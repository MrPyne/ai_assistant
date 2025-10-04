import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Login(){
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    if (!email || !password) return alert('email and password required')
    try {
      const resp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (resp.ok) {
        const data = await resp.json()
        if (data && data.access_token) {
          localStorage.setItem('authToken', data.access_token)
          alert('Logged in')
          navigate('/')
        }
      } else {
        const txt = await resp.text()
        alert('Login failed: ' + txt)
      }
    } catch (err) {
      alert('Login error: ' + String(err))
    }
  }

  return (
    <div style={{ padding: 20 }}>
      <h3>Login</h3>
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 8, width: 360 }}>
        <input placeholder='email' value={email} onChange={(e) => setEmail(e.target.value)} />
        <input placeholder='password' type='password' value={password} onChange={(e) => setPassword(e.target.value)} />
        <div style={{ display: 'flex', gap: 8 }}>
          <button type='submit'>Login</button>
        </div>
      </form>
    </div>
  )
}
