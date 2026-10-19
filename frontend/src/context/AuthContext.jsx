import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { authApi } from '../api/endpoints'
import { getTokens, setTokens, clearTokens, getCachedUser, setCachedUser } from '../storage'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getCachedUser())
  const [booting, setBooting] = useState(true)

  // On mount: if we have tokens, validate them against /auth/me
  useEffect(() => {
    const { accessToken } = getTokens()
    if (!accessToken) { setBooting(false); return }
    authApi.me()
      .then((u) => { setUser(u); setCachedUser(u) })
      .catch(() => { clearTokens(); setUser(null) })
      .finally(() => setBooting(false))
  }, [])

  // Interceptor dispatches this when refresh fails -> force logout in UI
  useEffect(() => {
    const handler = () => { setUser(null); clearTokens() }
    window.addEventListener('auth:logout', handler)
    return () => window.removeEventListener('auth:logout', handler)
  }, [])

  const login = useCallback(async (username, password) => {
    const data = await authApi.login({ username, password })
    setTokens(data.access_token, data.refresh_token)
    setCachedUser(data.user)
    setUser(data.user)
    return data.user
  }, [])

  const register = useCallback(async (payload) => {
    const data = await authApi.register(payload)
    setTokens(data.access_token, data.refresh_token)
    setCachedUser(data.user)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(async () => {
    const { refreshToken } = getTokens()
    try { await authApi.logout(refreshToken) } catch { /* already-invalid token is fine */ }
    clearTokens()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, booting, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
