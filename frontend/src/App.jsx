import React from 'react'
import './index.css'
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import NavBar from './components/NavBar'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import Profile from './pages/Profile'
import Editor from './editor'

function RequireAuth({ children }) {
  const { token } = useAuth()
  if (!token) return <Navigate to="/login" replace />
  return children
}

export default function App(){
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app-shell">
          <div className="topbar">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <h2 className="brand" style={{ margin: 0 }}><Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>No-code AI</Link></h2>
            </div>
            <div style={{ flex: 1 }} />
            <div className="nav">
              <NavBar />
            </div>
          </div>

          <div className="main">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
              <Route path="/editor" element={<RequireAuth><Editor /></RequireAuth>} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </AuthProvider>
  )
}
