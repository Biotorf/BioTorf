<script setup>
import { computed } from 'vue';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';

const ui = useUiStore();
const { ROLES } = usePermissions();

const MENU = [
  ['dashboard', '▦', 'Обзор'],
  ['crm', '♙', 'Клиенты и хозяйства'],
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
  director: MENU.map((m) => m[0]),
  operations: ['dashboard', 'crm', 'pilots', 'knowledge', 'social', 'orders', 'production', 'warehouse', 'shipments', 'finance', 'tasks', 'analytics'],
  // ... остальные роли 1:1 из исходника
};

const visibleMenu = computed(() => {
  const avail = VIS[ui.role] || VIS.director;
  return MENU.filter((m) => avail.includes(m[0]));
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
      ОсОО «Агро Трейд Плюс»
      <p style="margin:6px 0 0">
        Прототип на обезличенных данных. Переключение ролей — демонстрация.
      </p>
    </div>
  </aside>
</template>