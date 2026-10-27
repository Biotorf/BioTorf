<script setup>
// Реестр сотрудников и выдача ролей.
// Право изменять роли есть только у генерального директора (проверяется и
// на сервере — PUT /api/users/{login}/role отвечает 403 остальным).
import { ref, computed, onMounted } from 'vue';
import { COMMS_API_URL, checkApi } from '@/api/commsClient';
import { authHeaders, logout } from '@/api/authClient';
import { useUiStore } from '@/stores/ui';

const ui = useUiStore();

const items = ref([]);
const roles = ref({});
const canManage = ref(false);
const online = ref(true);
const error = ref('');
const busyLogin = ref('');
const showPending = computed(() => items.value.filter((u) => u.role === 'pending').length);

async function load() {
  if (!(await checkApi())) { online.value = false; return; }
  try {
    const resp = await fetch(COMMS_API_URL + '/api/users', {
      headers: { ...authHeaders() }, signal: AbortSignal.timeout(8000),
    });
    if (resp.status === 401) { logout(); return; }   // сессия истекла → экран входа
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    items.value = data.items;
    roles.value = data.roles;
    canManage.value = data.canManage;
    error.value = '';
  } catch (e) { error.value = e.message || 'Сервер недоступен'; }
}

async function setRole(loginName, role) {
  busyLogin.value = loginName; error.value = '';
  try {
    const resp = await fetch(`${COMMS_API_URL}/api/users/${encodeURIComponent(loginName)}/role`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ role }), signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) throw new Error((await resp.json()).detail || `HTTP ${resp.status}`);
    await load();
  } catch (e) { error.value = e.message; }
  finally { busyLogin.value = ''; }
}

async function removeUser(loginName) {
  if (!confirm(`Удалить аккаунт «${loginName}»?`)) return;
  busyLogin.value = loginName; error.value = '';
  try {
    const resp = await fetch(`${COMMS_API_URL}/api/users/${encodeURIComponent(loginName)}`, {
      method: 'DELETE', headers: { ...authHeaders() }, signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok && resp.status !== 204) throw new Error((await resp.json()).detail || `HTTP ${resp.status}`);
    await load();
  } catch (e) { error.value = e.message; }
  finally { busyLogin.value = ''; }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Сотрудники и роли</h1>
        <p class="subtitle">Первый зарегистрированный аккаунт — генеральный директор. Только он выдаёт роли остальным.</p>
      </div>
      <button class="btn slim" @click="load">⟳ Обновить</button>
    </div>

    <p v-if="!online" class="note">Бэкенд недоступен — реестр сотрудников живёт на сервере, подключите API.</p>
    <p v-if="error" class="note">{{ error }}</p>
    <p v-if="canManage && showPending" class="note">
      ⚠ Ожидают подтверждения роли: {{ showPending }} сотрудник(а). Выдайте роль из таблицы ниже — после этого они смогут войти в систему.
    </p>
    <p v-if="!canManage" class="note">Просмотр. Менять роли может только генеральный директор.</p>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr><th>Логин</th><th>Имя</th><th>Должность</th><th>Контакты</th><th>Роль</th><th>Статус</th><th>Создан</th><th v-if="canManage">Действия</th></tr>
        </thead>
        <tbody>
          <tr v-for="u in items" :key="u.login">
            <td class="mono">{{ u.login }}</td>
            <td>{{ u.name || '—' }}</td>
            <td>{{ u.position || '—' }}</td>
            <td class="text-muted" style="font-size:11.5px">
              <div v-if="u.phone">{{ u.phone }}</div>
              <div v-if="u.email">{{ u.email }}</div>
              <div v-if="!u.phone && !u.email">—</div>
            </td>
            <td>
              <select v-if="canManage && u.login !== ui.login" class="select" :value="u.role"
                      :disabled="busyLogin === u.login"
                      @change="setRole(u.login, $event.target.value)">
                <option value="pending">⏳ Ожидает подтверждения</option>
                <option v-for="(label, key) in roles" :key="key" :value="key">{{ label }}</option>
              </select>
              <span v-else>{{ roles[u.role] || u.role }}</span>
            </td>
            <td>
              <span v-if="u.role === 'pending'" class="pill amber">ожидает</span>
              <span v-else-if="u.role === 'director'" class="pill">генеральный директор</span>
              <span v-else class="pill gray">активен</span>
            </td>
            <td class="text-muted">{{ (u.created_at || '').slice(0, 10) }}</td>
            <td v-if="canManage">
              <button v-if="u.login !== ui.login" class="btn ghost slim"
                      :disabled="busyLogin === u.login" @click="removeUser(u.login)">✕</button>
            </td>
          </tr>
          <tr v-if="!items.length && online"><td colspan="8" class="empty">Сотрудников пока нет.</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
