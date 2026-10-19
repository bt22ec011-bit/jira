export function Spinner({ label = 'Loading…' }) {
  return <div className="state-box"><span className="spinner" /> {label}</div>
}

export function EmptyState({ title, hint }) {
  return (
    <div className="state-box empty">
      <div className="empty-title">{title}</div>
      {hint && <div className="empty-hint">{hint}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="state-box error">
      <div>⚠️ {message || 'Failed to load data'}</div>
      {onRetry && <button className="btn small" onClick={onRetry}>Try again</button>}
    </div>
  )
}
