// Клиент реестра каналов и подключённых аккаунтов CRM (backend /api/channels).
// Управление — раздел «Настройки → Каналы» (права на запись: admin-секция,
// т.е. директор/операционный руководитель на сервере).
import { COMMS_API_URL } from './commsClient';

async function req(path, options = {}) {
  const { authHeaders } = await import('./authClient');
  const resp = await fetch(COMMS_API_URL + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(options.headers || {}) },
    signal: AbortSignal.timeout(8000),
  });
  if (!resp.ok) throw new Error(`Channels API ${resp.status}: ${await resp.text()}`);
  if (resp.status === 204) return null;
  return resp.json();
}

export const channelsApi = {
  /** Список каналов (+подключённые аккаунты, секреты замаскированы) и пресеты. */
  list: () => req('/api/channels'),

  /** Добавить канал из пресета или вручную: {label, icon, color, group}. */
  add: (kind, data) => req(`/api/channels?kind=${encodeURIComponent(kind)}`, {
    method: 'POST', body: JSON.stringify(data || {}),
  }),

  /** Включить/отключить канал, переименовать. */
  patch: (kind, data) => req(`/api/channels/${encodeURIComponent(kind)}`, {
    method: 'PATCH', body: JSON.stringify(data),
  }),

  /** Подключить аккаунт канала: {login, token?, secret?, displayName?, farmId?}. */
  connect: (kind, data) => req(`/api/channels/${encodeURIComponent(kind)}/accounts`, {
    method: 'POST', body: JSON.stringify(data),
  }),

  updateAccount: (id, data) => req(`/api/channel-accounts/${encodeURIComponent(id)}`, {
    method: 'PATCH', body: JSON.stringify(data),
  }),

  removeAccount: (id) => req(`/api/channel-accounts/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }),
};
