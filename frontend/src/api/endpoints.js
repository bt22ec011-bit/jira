import { api } from './client'

// --- Auth -----------------------------------------------------------------------
export const authApi = {
  register: (data) => api.post('/auth/register', data).then(r => r.data),
  login: (data) => api.post('/auth/login', data).then(r => r.data),
  logout: (refreshToken) => api.post('/auth/logout', { refresh_token: refreshToken }).then(r => r.data),
  me: () => api.get('/auth/me').then(r => r.data.user),
}

// --- Projects -------------------------------------------------------------------
export const projectApi = {
  list: () => api.get('/projects').then(r => r.data),
  get: (id) => api.get(`/projects/${id}`).then(r => r.data),
  create: (data) => api.post('/projects', data).then(r => r.data),
  update: (id, data) => api.put(`/projects/${id}`, data).then(r => r.data),
  addMember: (id, data) => api.post(`/projects/${id}/members`, data).then(r => r.data),
  removeMember: (id, userId) => api.delete(`/projects/${id}/members/${userId}`).then(r => r.data),
  users: (id) => api.get(`/projects/${id}/users`).then(r => r.data),
  labels: (id) => api.get(`/projects/${id}/labels`).then(r => r.data),
  createLabel: (id, data) => api.post(`/projects/${id}/labels`, data).then(r => r.data),
  deleteLabel: (id, labelId) => api.delete(`/projects/${id}/labels/${labelId}`).then(r => r.data),
  activity: (projectId, limit = 30) =>
    api.get('/issues/activity', { params: { project_id: projectId, limit } }).then(r => r.data),
}

// --- Issues ---------------------------------------------------------------------
export const issueApi = {
  list: (params) => api.get('/issues', { params }).then(r => r.data),
  counts: (projectId) =>
    api.get('/issues/counts', { params: projectId ? { project_id: projectId } : {} }).then(r => r.data),
  get: (id) => api.get(`/issues/${id}`).then(r => r.data),
  create: (data) => api.post('/issues', data).then(r => r.data),
  update: (id, data) => api.put(`/issues/${id}`, data).then(r => r.data),
  transition: (id, toState) => api.post(`/issues/${id}/transition`, { to_state: toState }).then(r => r.data),
  comment: (id, body) => api.post(`/issues/${id}/comments`, { body }).then(r => r.data),
  activity: (id) => api.get(`/issues/${id}/activity`).then(r => r.data),
}
