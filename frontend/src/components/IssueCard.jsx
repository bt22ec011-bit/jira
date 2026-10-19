import { PRIORITY_COLORS, TYPE_ICONS } from '../constants'

// Compact card shown in Kanban columns and lists.
export default function IssueCard({ issue, onClick, draggable = false, onDragStart, dimmed = false }) {
  return (
    <div
      className={`issue-card${dimmed ? ' dimmed' : ''}`}
      onClick={onClick}
      draggable={draggable}
      onDragStart={onDragStart}
      title={draggable ? 'Drag to move between columns' : ''}
    >
      <div className="card-top">
        <span className="issue-key">{issue.key}</span>
        <span className="type-icon" title={issue.type}>{TYPE_ICONS[issue.type]}</span>
        <span className="prio-dot" style={{ background: PRIORITY_COLORS[issue.priority] }}
              title={`Priority: ${issue.priority}`} />
      </div>
      <div className="card-title">{issue.title}</div>
      {issue.labels?.length > 0 && (
        <div className="card-labels">
          {issue.labels.map((l) => <span key={l} className="label-chip">{l}</span>)}
        </div>
      )}
      <div className="card-bottom">
        <span className="assignee-avatar" title={issue.assignee_name || 'Unassigned'}>
          {issue.assignee_name ? issue.assignee_name[0] : '—'}
        </span>
        {issue.due_date && <span className="due">{String(issue.due_date).slice(0, 10)}</span>}
      </div>
    </div>
  )
}
