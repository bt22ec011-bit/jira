// Shared Axios instance. The API URL is never hardcoded in components:
// - dev: Vite proxies /api -> Flask (see vite.config.js)
// - docker: nginx proxies /api -> gunicorn
import axios from 'axios'
import { getTokens, setTokens, clearTokens } from '../storage'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
})

// --- Request interceptor: attach the access token -------------------------------
api.interceptors.request.use((config) => {
  const { accessToken } = getTokens()
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

// --- Response interceptor: on 401 refresh once, retry original, else logout -----
let refreshPromise = null

async function refreshTokens() {
  const { refreshToken } = getTokens()
  if (!refreshToken) throw new Error('No refresh token')
  // bare axios (not `api`) so a failing refresh cannot loop through interceptors
  const res = await axios.post(
    (import.meta.env.VITE_API_URL || '/api') + '/auth/refresh',
    {},
    { headers: { Authorization: `Bearer ${refreshToken}` } },
  )
  setTokens(res.data.access_token, res.data.refresh_token)
  return res.data.access_token
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    const status = error.response?.status
    if (status === 401 && !original._retried && !original.url.includes('/auth/')) {
      original._retried = true
      try {
        // attempt a refresh once (dedupe concurrent refreshes)
        refreshPromise = refreshPromise || refreshTokens()
        const newAccess = await refreshPromise
        refreshPromise = null
        original.headers.Authorization = `Bearer ${newAccess}`
        return api(original) // retry the original request once
      } catch {
        refreshPromise = null
        // refresh failed -> log out
        const rt = getTokens().refreshToken
        clearTokens()
        window.dispatchEvent(new CustomEvent('auth:logout'))
        if (rt) {
          // best-effort server-side invalidation of the refresh token
          axios.post((import.meta.env.VITE_API_URL || '/api') + '/auth/logout',
            { refresh_token: rt }).catch(() => {})
        }
      }
    }
    return Promise.reject(error)
  },
)

// Helper to extract a readable message from an API error
export function errMsg(e, fallback = 'Something went wrong') {
  return e?.response?.data?.error || e?.message || fallback
}
