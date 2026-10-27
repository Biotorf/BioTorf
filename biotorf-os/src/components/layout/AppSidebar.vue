<script setup>
import { computed } from 'vue';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { logout } from '@/api/authClient';

const ui = useUiStore();
const { ROLES } = usePermissions();

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
  director: [...MENU.map((m) => m[0]), 'employees'],
  operations: ['dashboard', 'crm', 'comms', 'pilots', 'knowledge', 'social', 'orders', 'production', 'warehouse', 'shipments', 'finance', 'tasks', 'analytics'],
  // ... остальные роли 1:1 из исходника
};

// ключи разделов, которые видны всем ролям (общая рабочая лента связи)
const ALWAYS = ['comms'];

// «Сотрудники и роли» — виден всем, но управлять может только директор
// (сервер всё равно проверяет право на выдачу ролей)
const FULL_MENU = [...MENU, ['employees', '♟', 'Сотрудники и роли']];

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