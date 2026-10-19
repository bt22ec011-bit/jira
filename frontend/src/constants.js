// UI constants mirroring the backend workflow configuration.

export const STATES = ['Backlog', 'To Do', 'In Progress', 'In Review', 'Done']

// Kept in sync with backend/app/config.py ALLOWED_TRANSITIONS (the backend is
// authoritative; this is only used to grey-out obviously illegal drops early).
export const ALLOWED_TRANSITIONS = {
  Backlog: ['To Do'],
  'To Do': ['Backlog', 'In Progress'],
  'In Progress': ['To Do', 'In Review'],
  'In Review': ['In Progress', 'Done'],
  Done: ['In Review'],
}

export const PRIORITIES = ['Low', 'Medium', 'High', 'Urgent']
export const ISSUE_TYPES = ['bug', 'task', 'story']

export const PRIORITY_COLORS = {
  Low: '#6b7280', Medium: '#3b82f6', High: '#f59e0b', Urgent: '#ef4444',
}

export const TYPE_ICONS = { bug: '🐞', task: '✅', story: '📗' }

export const STATE_COLORS = {
  Backlog: '#94a3b8', 'To Do': '#60a5fa', 'In Progress': '#fbbf24',
  'In Review': '#a78bfa', Done: '#34d399',
}
