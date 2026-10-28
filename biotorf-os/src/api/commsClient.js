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
  // JWT авторизованного сотрудника (см. authClient); в DEMO-режиме пусто
  const { authHeaders } = await import('./authClient');
  const resp = await fetch(COMMS_API_URL + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(options.headers || {}) },
    signal: AbortSignal.timeout(5000),
  });
  if (!resp.ok) throw new Error(`Comms API ${resp.status}: ${await resp.text()}`);
  if (resp.status === 204) return null;
  return resp.json();
}

let healthPromise = null;
let healthTimer = null;
export function checkApi() {
  healthPromise ??= req('/health')
    .then(() => { apiState.online = true; return true; })
    .catch(() => { apiState.online = false; return false; });
  // фоновый watchdog: если бэкенд (или telegram-worker) упал и снова поднялся,
  // лента должна «вернуться к жизни» без перезагрузки страницы — иначе
  // входящие Telegram-сообщения перестают приходить на сайт молча
  if (!healthTimer && typeof setInterval === 'function') {
    healthTimer = setInterval(() => {
      healthPromise = null;
      checkApi();
    }, 30000);
  }
  return healthPromise;
}

// Возможности сервера (что настроено): telegramSend / whatsappSend.
// Подтягивается при синхронизации ленты; по умолчанию считаем что отправки нет.
export const caps = { telegramSend: false, telegramBot: null, whatsappSend: false, whatsappPhone: null, whatsappError: null };

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
  // Реальный ответ клиенту: POST /api/comms/{id}/send → sendMessage в Telegram
  send: (id, text) => req(`/api/comms/${id}/send`, { method: 'POST', body: JSON.stringify({ text }) }),
  capabilities: () => req('/api/capabilities').then((c) => Object.assign(caps, c)),
  // ── мессенджер: диалоги-чаты ────────────────────────────────────────────
  chats: (limit = 200) => req(`/api/chat-list?limit=${limit}`),
  chat: (peerKey) => req(`/api/chat/${encodeURIComponent(peerKey)}`),
  markChatRead: (peerKey) => req(`/api/chat/${encodeURIComponent(peerKey)}/read`, { method: 'POST' }),
  saveDraft: (peerKey, draft) => req(`/api/chat/${encodeURIComponent(peerKey)}/draft`, { method: 'PUT', body: JSON.stringify({ draft }) }),
  sendToChat: (peerKey, text, kind = null) => req(`/api/chat/${encodeURIComponent(peerKey)}/send`, { method: 'POST', body: JSON.stringify({ text, kind }) }),
};
