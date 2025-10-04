import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function NavBar(){
  const { token, setToken } = useAuth()
  const navigate = useNavigate()

  const logout = () => {
    setToken('')
    navigate('/')
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <h2 style={{ margin: 0 }}><Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>No-code AI Assistant</Link></h2>
      <nav style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <Link to="/">Home</Link>
        <Link to="/editor">Editor</Link>
        {token ? (<>
          <Link to="/profile">Profile</Link>
          <button onClick={logout}>Logout</button>
        </>) : (
          <>
            <Link to="/login">Login</Link>
            <Link to="/register">Register</Link>
          </>
        )}
      </nav>
    </div>
  )
}
