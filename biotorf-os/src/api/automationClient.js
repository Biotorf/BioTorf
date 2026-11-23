import { COMMS_API_URL } from './commsClient';
import { authHeaders } from './authClient';

async function request(path, options = {}) {
  const response = await fetch(COMMS_API_URL + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    signal: AbortSignal.timeout(8000),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Не удалось открыть автоматизацию (HTTP ${response.status}).`);
  return data;
}

export const automationApi = {
  list: () => request('/api/automation/rules'),
  update: (id, enabled) => request('/api/automation/rules/' + encodeURIComponent(id), {
    method: 'PUT', body: JSON.stringify({ enabled }),
  }),
};
