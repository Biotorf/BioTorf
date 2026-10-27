// Клиент CRM API бэкенда (backend/crm.py, FastAPI + SQLite).
// Двухрежимный, как commsClient/logisticsClient:
//   • бэкенд поднят  — все сотрудники работают с общей базой (state-sync);
//   • бэкенда нет    — фронтенд остаётся на localStorage (демо-режим v0.9).
import { COMMS_API_URL, checkApi } from './commsClient';

async function req(path, options = {}) {
  const { authHeaders } = await import('./authClient');
  const resp = await fetch(COMMS_API_URL + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(options.headers || {}) },
    signal: AbortSignal.timeout(8000),
  });
  if (!resp.ok) throw new Error(`CRM API ${resp.status}: ${await resp.text()}`);
  if (resp.status === 204) return null;
  return resp.json();
}

export const crmApi = {
  online: () => checkApi(),
  getState: () => req('/api/crm/state'),
  putState: (payload) => req('/api/crm/state', { method: 'PUT', body: JSON.stringify(payload) }),
  seed: (payload) => req('/api/crm/seed', { method: 'POST', body: JSON.stringify(payload) }),
  list: (coll) => req(`/api/crm/${coll}`).then((r) => r.items),
  create: (coll, rec) => req(`/api/crm/${coll}`, { method: 'POST', body: JSON.stringify(rec) }),
  update: (coll, id, patch) => req(`/api/crm/${coll}/${id}`, { method: 'PUT', body: JSON.stringify(patch) }),
  remove: (coll, id) => req(`/api/crm/${coll}/${id}`, { method: 'DELETE' }),
  journeyProcess: (journeyId) => req(`/api/crm/journeys/${journeyId}/process`),
};
