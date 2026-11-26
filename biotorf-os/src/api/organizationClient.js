import { authHeaders } from './authClient';
import { COMMS_API_URL } from './commsClient';

async function request(method, data) {
  const response = await fetch(COMMS_API_URL + '/api/organization', {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(15000),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : `Не удалось загрузить или сохранить реквизиты (HTTP ${response.status}).`);
  }
  return payload;
}

export const organizationApi = {
  get: () => request('GET'),
  save: (data) => request('PUT', data),
};
