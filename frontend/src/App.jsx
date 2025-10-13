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
import AuditLogs from './pages/AuditLogs'
import Schedulers from './pages/Schedulers'

// Lazy-load the editor and the EditorProvider to reduce chance of circular
// initialization / TDZ issues during bundling.
const LazyEditor = React.lazy(() => import('./editor'))
const LazyEditorProvider = React.lazy(() => import('./state/EditorContext').then(m => ({ default: m.EditorProvider })))

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(err) {
    return { hasError: true, error: err }
  }

  componentDidCatch(err, info) {
    console.error('ErrorBoundary caught', err, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 20 }}>
          <h3>Something went wrong rendering this area</h3>
          <pre style={{ whiteSpace: 'pre-wrap', color: 'red' }}>{String(this.state.error && this.state.error.stack ? this.state.error.stack : this.state.error)}</pre>
        </div>
      )
    }
    return this.props.children
  }
}

function RequireAuth({ children }) {
  const { token } = useAuth()
  if (!token) return <Navigate to="/login" replace />

  return (
    <React.Suspense fallback={<div style={{ padding: 20 }}>Loading...</div>}>
      <LazyEditorProvider>
        <ErrorBoundary>{children}</ErrorBoundary>
      </LazyEditorProvider>
    </React.Suspense>
  )
}

function RequireAuthEditor() {
  const { token } = useAuth()
  if (!token) return <Navigate to="/login" replace />

  return (
    <React.Suspense fallback={<div style={{ padding: 20 }}>Loading editor...</div>}>
      <LazyEditorProvider>
        <ErrorBoundary>
          {/* Pass auth token down so the editor's left panel uses the real token for API calls */}
          <LazyEditor token={token} />
        </ErrorBoundary>
      </LazyEditorProvider>
    </React.Suspense>
  )
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
              <Route path="/editor" element={<RequireAuthEditor />} />
              <Route path="/secrets" element={<RequireAuth><Secrets /></RequireAuth>} />
              <Route path="/schedulers" element={<RequireAuth><Schedulers /></RequireAuth>} />
              <Route path="/audit_logs" element={<RequireAuth><AuditLogs /></RequireAuth>} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </AuthProvider>
  )
}
