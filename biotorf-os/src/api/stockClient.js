import { COMMS_API_URL } from './commsClient';
import { authHeaders } from './authClient';

export async function stock(path, method = 'GET', body) {
  const response = await fetch(COMMS_API_URL + '/api' + path, {
    method,
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(12000),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Не удалось выполнить складскую операцию.');
  return data;
}
