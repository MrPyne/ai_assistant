import React from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Editor from './editor'
import Login from './pages/Login'
import Register from './pages/Register'

export default function App(){
  return (
    <BrowserRouter>
      <div style={{ padding: 12, borderBottom: '1px solid #eee', display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>No-code AI Assistant</h2>
        <nav>
          <Link to="/">Editor</Link> {' | '} <Link to="/login">Login</Link> {' | '} <Link to="/register">Register</Link>
        </nav>
      </div>
      <Routes>
        <Route path="/" element={<Editor />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Routes>
    </BrowserRouter>
  )
}
