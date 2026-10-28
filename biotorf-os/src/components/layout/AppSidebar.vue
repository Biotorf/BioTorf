<script setup>
import { computed } from 'vue';
import { useUiStore } from '@/stores/ui';
import { useDbStore } from '@/stores/db';
import { usePermissions } from '@/composables/usePermissions';
import { logout } from '@/api/authClient';

const ui = useUiStore();
const db = useDbStore();
const { ROLES } = usePermissions();

// Разделы, полностью привязанные к бэкенду (данные читаются/пишутся через API).
const BACKEND_VIEWS = new Set([
  'crm', 'comms', 'pipeline', 'journey', 'pilots', 'orders', 'shipments',
  'finance', 'tasks', 'knowledge', 'warehouse', 'production', 'products',
  'social', 'media', 'analytics', 'calendar', 'notifications',
  'employees', 'channels',
]);
// Живой ли сервер — для цветовой отметки в меню.
const online = computed(() => db.serverOnline);

function onLogout() {
  logout();
  ui.clearSession();
  location.reload();
}

const MENU = [
  ['dashboard', '▦', 'Обзор'],
  ['crm', '♙', 'Клиенты и хозяйства'],
  ['comms', '☎', 'Коммуникации'],
  ['pipeline', '▥', 'Сделки и воронка'],
  ['journey', '⤳', 'Сквозной процесс'],
  ['pilots', '❧', 'Агрономия'],
  ['knowledge', '▤', 'База знаний'],
  ['social', '◉', 'Маркетинг и соцсети'],
  ['products', '◫', 'Продукция и цены'],
  ['orders', '▣', 'Заказы'],
  ['production', '⚙', 'Производство'],
  ['warehouse', '▤', 'Склад'],
  ['shipments', '➜', 'Логистика'],
  ['finance', '◈', 'Финансы'],
  ['tasks', '☑', 'Задачи'],
  ['analytics', '▥', 'Аналитика'],
  ['calendar', '▦', 'Календарь'],
  ['media', '▧', 'Медиатека'],
  ['notifications', '♢', 'Уведомления'],
];

const VIS = {
  director: [...MENU.map((m) => m[0]), 'employees', 'channels'],
  operations: ['dashboard', 'crm', 'comms', 'pilots', 'knowledge', 'social', 'orders', 'production', 'warehouse', 'shipments', 'finance', 'tasks', 'analytics', 'channels'],
  // ... остальные роли 1:1 из исходника
};

// ключи разделов, которые видны всем ролям (общая рабочая лента связи)
const ALWAYS = ['comms'];

// «Сотрудники и роли» — виден всем, но управлять может только директор
// (сервер всё равно проверяет право на выдачу ролей)
const FULL_MENU = [...MENU, ['employees', '♟', 'Сотрудники и роли'], ['channels', '🔌', 'Каналы CRM']];

const visibleMenu = computed(() => {
  const avail = VIS[ui.role] || VIS.director;
  return FULL_MENU.filter((m) => avail.includes(m[0]) || ALWAYS.includes(m[0]));
});
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">🌱</div>
      <div>
        <strong>BIOTORF</strong>
        <small>BUSINESS OS · v1.0</small>
      </div>
    </div>
    <div class="nav-label">РАБОЧАЯ СИСТЕМА</div>
    <nav class="nav">
      <button
        v-for="[key, icon, label] in visibleMenu"
        :key="key"
        :class="{ active: ui.view === key }"
        @click="ui.go(key)"
      >
        <b>{{ icon }}</b>{{ label }}
        <span
          v-if="BACKEND_VIEWS.has(key)"
          class="live-dot"
          :class="online ? 'on' : 'off'"
          :title="online ? 'Раздел работает с сервером' : 'Сервер недоступен — локальные данные'"
        ></span>
      </button>
    </nav>
    <div class="side-bottom">
      <template v-if="ui.login">
        {{ ui.name || ui.login }} · {{ ROLES[ui.role] || ui.role }}
        <p style="margin:6px 0 0">
          <button class="btn ghost slim" @click="onLogout">Выйти</button>
        </p>
      </template>
      <template v-else>
        ОсОО «Агро Трейд Плюс»
        <p style="margin:6px 0 0">Прототип на обезличенных данных.</p>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.nav button { position: relative; }
.live-dot {
  margin-left: auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.live-dot.on { background: #35d07f; box-shadow: 0 0 6px rgba(53, 208, 127, 0.7); }
.live-dot.off { background: #7c8f86; }
</style>