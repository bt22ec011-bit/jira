import { useAuth } from '../context/AuthContext'
import { NavLink, Link, Outlet, useNavigate } from 'react-router-dom'

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/projects" className="brand">🗂 IssueTracker</Link>
        <nav className="nav">
          <NavLink to="/projects">Projects</NavLink>
          <NavLink to="/my-issues">My Issues</NavLink>
        </nav>
        <div className="user-chip" title={`${user?.display_name} (${user?.role})`}>
          <span className="avatar" style={{ background: user?.avatar_color }}>
            {(user?.display_name || '?')[0]}
          </span>
          <span className="uname">{user?.username}</span>
          <span className={`role-badge role-${user?.role}`}>{user?.role}</span>
          <button className="btn small ghost" onClick={handleLogout}>Log out</button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
