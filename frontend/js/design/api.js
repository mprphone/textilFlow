import { get, patch, post, put, remove } from '../api.js?v=20260822-15';
import { state } from '../state.js';

const root = () => `/design/${state.companyId}`;

export const designApi = {
  pipeline: () => get(`${root()}/pipeline`),
  team: () => get(`${root()}/team`),
  today: () => get(`${root()}/today`),
  organization: () => get(`${root()}/organization`),
  report: (start, end) => get(`${root()}/report?start=${start}&end=${end}`),
  list: () => get(`${root()}/developments`),
  nextReference: (customerId, userId) => get(`${root()}/developments/next-reference?customer_id=${customerId}${userId ? `&user_id=${userId}` : ''}`),
  create: payload => post(`${root()}/developments`, payload),
  detail: id => get(`${root()}/developments/${id}`),
  move: (id, payload) => post(`${root()}/developments/${id}/move`, payload),
  patch: (id, payload) => patch(`${root()}/developments/${id}`, payload),
  addAssignee: (id, payload) => post(`${root()}/developments/${id}/assignees`, payload),
  removeAssignee: (id, assigneeId) => remove(`${root()}/developments/${id}/assignees/${assigneeId}`),
  addTask: (id, payload) => post(`${root()}/developments/${id}/tasks`, payload),
  updateTask: (id, taskId, payload) => patch(`${root()}/developments/${id}/tasks/${taskId}`, payload),
  removeTask: (id, taskId) => remove(`${root()}/developments/${id}/tasks/${taskId}`),
  addComment: (id, payload) => post(`${root()}/developments/${id}/comments`, payload),
  stageNote: (id, payload) => put(`${root()}/developments/${id}/stage-notes`, payload),
  remove: id => remove(`${root()}/developments/${id}`),
  production: (id, payload) => post(`${root()}/developments/${id}/production`, payload),
};

