import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function Login(){
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const { setToken } = useAuth()

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
          setToken(data.access_token)
          alert('Logged in')
          navigate('/editor')
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
    <div className="page">
      <div className="page-inner">
        <h3>Login</h3>
        <form onSubmit={submit} className="form-vertical">
          <input placeholder='email' value={email} onChange={(e) => setEmail(e.target.value)} />
          <input placeholder='password' type='password' value={password} onChange={(e) => setPassword(e.target.value)} />
          <div className="form-actions">
            <button type='submit'>Login</button>
          </div>
        </form>
      </div>
    </div>
  )
}
