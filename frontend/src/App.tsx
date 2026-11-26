import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import apiClient from './api/client'
import { DashboardLayout } from './layouts/DashboardLayout'
import { OverviewPage } from './pages/OverviewPage'
import { ChatPage } from './pages/ChatPage'
import { MemoryExplorerPage } from './pages/MemoryExplorerPage'
import { MemoryDetailPage } from './pages/MemoryDetailPage'
import { EditMemoryPage } from './pages/EditMemoryPage'
import { CreateMemoryPage } from './pages/CreateMemoryPage'
import { ConflictCenterPage } from './pages/ConflictCenterPage'
import { CustomInstructionsPage } from './pages/CustomInstructionsPage'
import { SettingsPage } from './pages/SettingsPage'

function App() {
  const [authChecked, setAuthChecked] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)
  const [authRequired, setAuthRequired] = useState(true)
  const [tokenInput, setTokenInput] = useState('')
  const [authError, setAuthError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let active = true
    apiClient
      .getAuthStatus()
      .then((status) => {
        if (!active) return
        setAuthenticated(status.authenticated)
        setAuthRequired(status.auth_required)
        setAuthChecked(true)
      })
      .catch(() => {
        if (!active) return
        setAuthChecked(true)
      })
    return () => {
      active = false
    }
  }, [])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)
    setSubmitting(true)
    try {
      await apiClient.loginOperator(tokenInput.trim())
      setTokenInput('')
      setAuthenticated(true)
    } catch {
      setAuthError('Invalid operator token. Check ~/.recall/.operator_token.')
    } finally {
      setSubmitting(false)
    }
  }

  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-zinc-300 text-sm">
        Checking RECALL operator session...
      </div>
    )
  }

  if (authRequired && !authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-zinc-100 p-4">
        <form
          onSubmit={handleLogin}
          className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-900 p-6 space-y-4 shadow-xl"
        >
          <h1 className="text-lg font-semibold">RECALL Operator Sign-In</h1>
          <p className="text-xs text-zinc-400">
            Enter your local operator token from <code className="text-zinc-200">~/.recall/.operator_token</code> to establish an HttpOnly session.
          </p>
          <input
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="Operator token"
            required
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
          />
          {authError && <p className="text-xs text-red-400">{authError}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-4 py-2 text-sm font-medium text-white"
          >
            {submitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/" element={<DashboardLayout />}>
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="overview" element={<OverviewPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="memories" element={<MemoryExplorerPage />} />
        <Route path="memories/new" element={<CreateMemoryPage />} />
        <Route path="memories/:id" element={<MemoryDetailPage />} />
        <Route path="memories/:id/edit" element={<EditMemoryPage />} />
        <Route path="conflicts" element={<ConflictCenterPage />} />
        <Route path="instructions" element={<CustomInstructionsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  )
}

export default App