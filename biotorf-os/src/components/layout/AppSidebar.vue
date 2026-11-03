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
  'employees',
]);
// Живой ли сервер — для цветовой отметки в меню.
const online = computed(() => db.serverOnline);

function onLogout() {
  logout();
  ui.clearSession();
  location.reload();
}

const GROUPS = [
  { label: 'ОБЗОР И ПРОЦЕСС', items: [
    ['dashboard', '▦', 'Обзор'],
    ['crm', '♙', 'Клиенты и хозяйства'],
    ['comms', '☎', 'Коммуникации'],
    ['pipeline', '▥', 'Сделки и воронка'],
    ['journey', '⤳', 'Сквозной процесс'],
    ['orders', '▣', 'Заказы'],
    ['shipments', '➜', 'Логистика'],
    ['tasks', '☑', 'Задачи'],
    ['calendar', '▦', 'Календарь'],
  ]},
  { label: 'ПРОИЗВОДСТВО И ТОРГИ', items: [
    ['products', '◫', 'Продукция и цены'],
    ['production', '⚙', 'Производство'],
    ['warehouse', '📦', 'Склад'],
    ['finance', '◈', 'Финансы'],
    ['pilots', '❧', 'Агрономия'],
    ['analytics', '▥', 'Аналитика'],
  ]},
  { label: 'МАРКЕТИНГ И ЗНАНИЯ', items: [
    ['social', '◉', 'Маркетинг и соцсети'],
    ['knowledge', '📖', 'База знаний'],
    ['media', '▧', 'Медиатека'],
    ['notifications', '♢', 'Уведомления'],
  ]},
  { label: 'УПРАВЛЕНИЕ', items: [
    ['employees', '♟', 'Сотрудники и роли'],
  ]},
];

const VIS = {
  director: GROUPS.flatMap((g) => g.items.map((m) => m[0])),
  operations: ['dashboard', 'crm', 'comms', 'pilots', 'knowledge', 'social', 'orders', 'production', 'warehouse', 'shipments', 'finance', 'tasks', 'analytics'],
  // ... остальные роли 1:1 из исходника
};

// ключи разделов, которые видны всем ролям (общая рабочая лента связи)
const ALWAYS = ['comms'];


const visibleMenu = computed(() => {
  const avail = VIS[ui.role] || VIS.director;
  return GROUPS.map((g) => ({ ...g, items: g.items.filter((m) => avail.includes(m[0]) || ALWAYS.includes(m[0])) })).filter((g) => g.items.length);
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
      <template v-for="g in visibleMenu" :key="g.label">
        <div class="group-label">{{ g.label }}</div>
        <button
          v-for="[key, icon, label] in g.items"
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
      </template>
    </nav>
    <a class="manual-nav" href="/manual.html#start" target="_blank" rel="noopener">
      📖 Книга пользователя<span class="qmark">?</span>
    </a>
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
.manual-nav {
  display: flex; align-items: center; gap: 8px; margin: 12px 10px 4px;
  padding: 9px 12px; border-radius: 10px; text-decoration: none;
  font-size: 13px; font-weight: 650; color: #dff0e5; background: rgba(255,255,255,.07);
  border: 1px solid rgba(255,255,255,.14); transition: background .15s ease;
}
.manual-nav:hover { background: rgba(255,255,255,.14); }
.manual-nav .qmark {
  margin-left: auto; width: 18px; height: 18px; border-radius: 50%;
  display: grid; place-items: center; font-size: 11px; font-weight: 800;
  background: #a7d3b4; color: #14382a;
}
.nav button { position: relative; }
.group-label { font-size: 10px; letter-spacing: .08em; color: #7c8f86; margin: 14px 10px 4px; font-weight: 600; }
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