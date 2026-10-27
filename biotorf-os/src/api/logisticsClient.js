// Клиент REST API логистики (поставки и выгрузки) — backend /api/logistics.
// Работает в тех же двух режимах, что и commsClient:
//   • бэкенд поднят  — документы общие для всех сотрудников (SQLite);
//   • бэкенда нет    — раздел работает локально в localStorage (демо-режим).
import { COMMS_API_URL, checkApi } from './commsClient';

async function req(path, options = {}) {
  const { authHeaders } = await import('./authClient');
  const resp = await fetch(COMMS_API_URL + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(options.headers || {}) },
    signal: AbortSignal.timeout(5000),
  });
  if (!resp.ok) throw new Error(`Logistics API ${resp.status}: ${await resp.text()}`);
  if (resp.status === 204) return null;
  return resp.json();
}

export const logisticsApi = {
  list: async (kind = null) => {
    const online = await checkApi();
    if (!online) return null;               // бэкенд недоступен — работаем локально
    const q = kind ? `?kind=${kind}` : '';
    const res = await req('/api/logistics' + q);
    return res.items;
  },
  create: (doc) => req('/api/logistics', { method: 'POST', body: JSON.stringify(doc) }),
  update: (id, doc) => req(`/api/logistics/${id}`, { method: 'PUT', body: JSON.stringify(doc) }),
  remove: (id) => req(`/api/logistics/${id}`, { method: 'DELETE' }),
};
