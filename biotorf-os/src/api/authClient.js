// Клиент авторизации BIOTORF Business OS.
// Бэкенд требует JWT (POST /auth/login) для всех /api/*; токен хранится в
// localStorage и подставляется в заголовок Authorization всеми API-клиентами
// (commsClient / crmClient / logisticsClient).
//
// Если бэкенд работает в DEV_MODE (AUTH_PASSWORD пуст), логин не требуется —
// authEnabled() вернёт false по флагу /health, и фронт продолжит работать
// как раньше (демо-режим).
import { COMMS_API_URL } from './commsClient';

const TOKEN_KEY = 'biotorf.auth.token';
const USER_KEY = 'biotorf.auth.user';

export const authState = {
  token: localStorage.getItem(TOKEN_KEY) || null,
  user: (() => { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } })(),
  // null = ещё не проверяли; true = сервер требует токен; false = DEV_MODE
  required: null,
};

export function authToken() { return authState.token; }

export function authHeaders() {
  return authState.token ? { Authorization: `Bearer ${authState.token}` } : {};
}

export function isAuthed() {
  return !!authState.token || authState.required === false;
}

export async function login(user, password, role) {
  const resp = await fetch(COMMS_API_URL + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user, password }),
    signal: AbortSignal.timeout(8000),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail || detail; } catch { /* html */ }
    throw new Error(detail);
  }
  const data = await resp.json();
  authState.token = data.token;
  authState.user = { name: data.user, role: data.role, roleName: data.roleName, roles: data.roles };
  authState.required = true;
  localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(USER_KEY, JSON.stringify(authState.user));
  return data;
}

export function logout() {
  authState.token = null;
  authState.user = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// Определяет, требует ли сервер авторизацию: если /health отдаёт
// authRequired:true (DEV_MODE выключен или пароль задан) — показываем логин.
export async function checkAuthRequired() {
  try {
    const resp = await fetch(COMMS_API_URL + '/health', { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) { authState.required = false; return false; }
    const info = await resp.json();
    authState.required = !!(info && info.authRequired);
    if (!authState.required) authState.user = authState.user || { name: 'dev', role: 'director', roleName: 'Генеральный директор' };
    return authState.required;
  } catch {
    authState.required = false;   // бэкенда нет — локальный демо-режим
    return false;
  }
}
