// Клиент бэкенда коммуникаций (backend/, FastAPI + SQLite, порт 8787).
//
// Фронтенд работает в двух режимах:
//   • бэкенд поднят  — лента «Коммуникации» синхронизируется с сервером
//     (общая база для всех сотрудников, вебхуки от Telegram/WhatsApp/телефонии);
//   • бэкенда нет    — всё остаётся локально в localStorage (демо-режим v0.9).
//
// URL бэкенда: VITE_COMMS_API из окружения сборки; если пусто — определяем по
// текущему хосту (в Docker-стеке фронт и API живут на одном origin, nginx
// проксирует /api, /webhooks, /health на backend). При npm run dev без
// явной переменной остаёмся на http://127.0.0.1:8787.
function resolveApiUrl() {
  const configured = import.meta.env?.VITE_COMMS_API;
  if (configured) return configured;
  if (typeof window !== 'undefined' && window.location && window.location.origin
      && !window.location.origin.startsWith('file:')) {
    return window.location.origin;   // прод/докер: тот же хост, что отдаёт фронт
  }
  return 'http://127.0.0.1:8787';    // локальная разработка вразноброс
}

export const COMMS_API_URL = resolveApiUrl();

// Флаг включается после успешного /health (см. checkApi)
export const apiState = { online: false };
export function apiEnabled() {
  return apiState.online;
}

async function req(path, options = {}) {
  const resp = await fetch(COMMS_API_URL + path, {
    headers: { 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(5000),
    ...options,
  });
  if (!resp.ok) throw new Error(`Comms API ${resp.status}: ${await resp.text()}`);
  if (resp.status === 204) return null;
  return resp.json();
}

let healthPromise = null;
export function checkApi() {
  healthPromise ??= req('/health')
    .then(() => { apiState.online = true; return true; })
    .catch(() => { apiState.online = false; return false; });
  return healthPromise;
}

export const commsApi = {
  list: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, v);
    });
    const qs = q.toString();
    return req('/api/comms' + (qs ? `?${qs}` : ''));
  },
  create: (entry) => req('/api/comms', { method: 'POST', body: JSON.stringify(entry) }),
  markRead: (id) => req(`/api/comms/${id}/read`, { method: 'POST' }),
  readAll: () => req('/api/comms/read-all', { method: 'POST' }),
  link: (id, farmId) => req(`/api/comms/${id}/link?farmId=${encodeURIComponent(farmId)}`, { method: 'POST' }),
  stats: () => req('/api/stats'),
};
