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
    <div className="header">
      <nav className="nav-inline">
        <Link to="/" className="nav-link">Home</Link>
        <Link to="/editor" className="nav-link">Editor</Link>
        {token ? (
          <>
            <Link to="/profile" className="nav-link">Profile</Link>
            <button onClick={logout} className="btn btn-ghost">Logout</button>
          </>
        ) : (
          <>
            <Link to="/login" className="nav-link">Login</Link>
            <Link to="/register" className="nav-link">Register</Link>
          </>
        )}
      </nav>
    </div>
  )
}
