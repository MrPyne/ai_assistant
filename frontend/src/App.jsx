import React from 'react'
import './index.css'
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import NavBar from './components/NavBar'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import Profile from './pages/Profile'
import Secrets from './pages/Secrets'
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
            <div className="topbar-left">
              <div className="brand">
                <Link to="/" className="brand-link">
                  <span className="logo" />
                  <div>
                    <div className="brand-title">No-code AI</div>
                    <div className="brand-sub">Workflows & automations</div>
                  </div>
                </Link>
              </div>
            </div>
            <div className="spacer" />
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
              <Route path="/secrets" element={<RequireAuth><Secrets /></RequireAuth>} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </AuthProvider>
  )
}
