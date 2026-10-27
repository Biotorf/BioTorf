// Клиент авторизации BIOTORF Business OS.
//
// Бэкенд требует JWT (POST /auth/login) для всех /api/*; токен хранится в
// localStorage и подставляется в заголовок Authorization всеми API-клиентами
// (commsClient / crmClient / logisticsClient — см. authHeaders()).
//
// Регистрация: POST /auth/register. ПЕРВЫЙ зарегистрированный аккаунт
// автоматически становится генеральным директором (роль director, токен
// выдаётся сразу). Все последующие получают роль «pending»: войти могут,
// но доступ к данным откроет только директор, выдав роль в разделе
// «Сотрудники».
//
// Если бэкенд работает в DEV_MODE (AUTH_PASSWORD пуст, сотрудников нет),
// authState.required === false — экран входа не показывается (демо-режим).
import { COMMS_API_URL } from './commsClient';

const TOKEN_KEY = 'biotorf.auth.token';
const USER_KEY = 'biotorf.auth.user';

export const authState = {
  token: localStorage.getItem(TOKEN_KEY) || null,
  user: (() => { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } })(),
  // null = ещё не проверяли; true = сервер требует токен; false = DEV_MODE
  required: null,
  hasUsers: true,
};

export function authToken() { return authState.token; }

export function authHeaders() {
  return authState.token ? { Authorization: `Bearer ${authState.token}` } : {};
}

export function isAuthed() {
  return !!authState.token || authState.required === false;
}

async function post(path, body) {
  const resp = await fetch(COMMS_API_URL + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(8000),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail || detail; } catch { /* html */ }
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  return resp.json();
}

// ── профиль своего аккаунта (/api/me/*) ──────────────────────────────────────
async function apiFetch(path, opts = {}) {
  const resp = await fetch(COMMS_API_URL + path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(opts.headers || {}) },
    signal: AbortSignal.timeout(8000),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail || detail; } catch { /* html */ }
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  return resp.status === 204 ? null : resp.json();
}

export function getMyProfile() { return apiFetch('/api/me/profile'); }
export function saveMyProfile(data) { return apiFetch('/api/me/profile', { method: 'PATCH', body: JSON.stringify(data) }); }
export function changeMyPassword(oldPassword, newPassword) {
  return apiFetch('/api/me/password', { method: 'POST', body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }) });
}

// Успешный вход → { token, user, name, role, roleName, roles }.
// pending-аккаунт → { pending: true, ... } — тоже сохраняем сессию (токен из
// /auth/login для pending не выдаётся, но бэкенд пускает такого пользователя
// в /api/me/* по его персональному токену, чтобы он заполнил профиль).
export async function login(user, password) {
  const data = await post('/auth/login', { user, password });
  if (data.token) applySession(data);   // в т.ч. pending: токен пустой по правам,
  return data;                          // но даёт доступ к /api/me/* и мини-профилю
}

// Регистрация сотрудника. Первый аккаунт → сразу сессия директора
// (data.firstAccount === true, есть token). Остальные → pending без токена:
// вход им не нужен, чтобы заполнить профиль (см. /auth/login для pending).
export async function register(user, password, name = '') {
  const data = await post('/auth/register', { user, password, name });
  if (data.token) applySession(data);
  return data;
}

// Вход сразу после регистрации (в т.ч. pending) — возвращает ответ /auth/login.
export function loginAfterRegister(user, password) {
  return login(user, password);
}

export function applySession(data) {
  authState.token = data.token;
  authState.user = {
    login: data.user, name: data.name || data.user,
    role: data.role, roleName: data.roleName, roles: data.roles,
  };
  authState.required = true;
  localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(USER_KEY, JSON.stringify(authState.user));
}

export function logout() {
  authState.token = null;
  authState.user = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// Определяет, требует ли сервер авторизацию, и есть ли уже сотрудники.
// hasUsers=false + authRequired=true → на экране входа предлагаем
// «зарегистрировать первого сотрудника — он станет генеральным директором».
export async function checkAuthRequired() {
  try {
    const resp = await fetch(COMMS_API_URL + '/health', { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) { authState.required = false; return false; }
    const info = await resp.json();
    authState.hasUsers = !!info.hasUsers;
    authState.required = !!(info && info.authRequired);
    if (!authState.required) {
      authState.user = authState.user || { login: 'dev', name: 'Разработчик', role: 'director', roleName: 'Генеральный директор' };
    }
    return authState.required;
  } catch {
    authState.required = false;   // бэкенда нет — локальный демо-режим
    authState.hasUsers = true;
    return false;
  }
}
