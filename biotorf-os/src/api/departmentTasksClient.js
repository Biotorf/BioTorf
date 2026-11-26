import { authHeaders } from './authClient';
import { COMMS_API_URL } from './commsClient';

async function request(method, suffix = '', payload) {
  const response = await fetch(COMMS_API_URL + '/api/department-tasks' + suffix, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: payload === undefined ? undefined : JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const fallback = response.status === 422 ? 'Проверьте обязательные поля задачи.' : `Ошибка сервера (${response.status}).`;
    throw new Error(typeof data?.detail === 'string' ? data.detail : fallback);
  }
  return data;
}

export const departmentTasksApi = {
  list: () => request('GET'),
  create: (data) => request('POST', '', data),
  update: (id, data) => request('PATCH', '/' + encodeURIComponent(id), data),
};
