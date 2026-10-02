import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { ApiTestingRoutes } from './modules/api-testing/index.jsx'
import { status } from './api.js'

// The NAV comes from the backend (GET /api/modules), so registering a module
// puts it in the sidebar without editing any nav code here. A module with no
// route in this file still shows up, and lands on "not implemented yet"
// instead of silently disappearing.
export default function App() {
  const [modules, setModules] = useState([])
  const [error, setError] = useState('')
  const [ollama, setOllama] = useState(null)

  useEffect(() => {
    fetch('/api/modules')
      .then((r) => r.json())
      .then(setModules)
      .catch(() => setError('Cannot reach the AutomationApp server.'))
    status()
      .then(setOllama)
      .catch(() => setOllama({ ollama_available: false, model: '?' }))
  }, [])

  const firstSlug = modules.length ? modules[0].slug : 'api-testing'

  return (
    <div className="layout">
      <nav className="sidebar">
        <h1>AutomationApp</h1>
        <div className="sub">Dashboard</div>
        {modules.map((m) => (
          <NavLink
            key={m.slug}
            to={`/${m.slug}`}
            className={({ isActive }) => (isActive ? 'active' : '')}
            title={m.description}
          >
            {m.title}
          </NavLink>
        ))}
        {modules.length === 0 && <div className="sub">Loading…</div>}
        {modules
          .filter((m) => m.slug !== 'api-testing')
          .map((m) => (
            <div key={m.slug} className="sub" style={{ padding: '9px 10px' }}>
              {m.title} <span className="badge">soon</span>
            </div>
          ))}
        {ollama && (
          <div className="sub" style={{ marginTop: 18, lineHeight: 1.5 }}>
            Model
            <br />
            <span className={ollama.ollama_available ? 'badge ok' : 'badge bad'}>
              {ollama.model}
            </span>
          </div>
        )}
      </nav>

      <main className="content">
        {error && <div className="notice error">{error}</div>}
        <Routes>
          <Route path="/" element={<Navigate to={`/${firstSlug}`} replace />} />
          <Route path="/api-testing/*" element={<ApiTestingRoutes />} />
          <Route path="*" element={<div className="notice warn">Page not found.</div>} />
        </Routes>
      </main>
    </div>
  )
}
