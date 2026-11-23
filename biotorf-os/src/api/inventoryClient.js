import { COMMS_API_URL } from './commsClient';

async function request(options = {}) {
  const { authHeaders } = await import('./authClient');
  const response = await fetch(COMMS_API_URL + '/api/inventory', {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    signal: AbortSignal.timeout(8000),
  });
  const data = await response.json().catch(() => null);
  if (response.status === 404 || response.status === 405 ||
      (response.ok && (!Array.isArray(data?.balances) || !Array.isArray(data?.events)))) {
    throw Object.assign(new Error('Сервер не предоставил складской журнал.'), { inventoryUnavailable: true });
  }
  if (!response.ok) {
    const detail = typeof data?.detail === 'string'
      ? data.detail
      : Array.isArray(data?.detail)
        ? data.detail.map((error) => error.msg).join('; ')
        : data?.detail?.message;
    throw new Error(detail || `Не удалось выполнить запрос к складу (HTTP ${response.status}).`);
  }
  return data;
}

export const inventoryApi = {
  list: () => request(),
  post: (event) => request({ method: 'POST', body: JSON.stringify(event) }),
};
