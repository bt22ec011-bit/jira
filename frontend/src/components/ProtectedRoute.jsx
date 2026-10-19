import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export function ProtectedRoute({ children }) {
  const { user, booting } = useAuth()
  const location = useLocation()
  if (booting) return <div className="center-msg">Loading…</div>
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  return children
}

export function AdminRoute({ children }) {
  const { user, booting } = useAuth()
  if (booting) return <div className="center-msg">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'admin') return <Navigate to="/projects" replace />
  return children
}
