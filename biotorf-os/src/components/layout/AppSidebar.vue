<script setup>
import { watch, ref } from 'vue';
import { useUiStore } from '@/stores/ui';

const ui = useUiStore();

const primary = [
  ['dashboard', '⌂', 'Главная'],
  ['comms', '✉', 'Входящие'],
  ['crm', '♙', 'Клиенты'],
  ['journey', '↗', 'Продажи'],
  ['shipments', '⇄', 'Поставки и отгрузки'],
  ['production', '⚙', 'Производство'],
  ['warehouse', '▣', 'Склад'],
];
const extra = [
  ['orders', 'Заказы'], ['finance', 'Финансы'], ['tasks', 'Задачи'],
  ['products', 'Каталог товаров'], ['pipeline', 'Воронка сделок'], ['pilots', 'Агрономия'],
  ['registry', 'Все таблицы'], ['calendar', 'Календарь'], ['analytics', 'Аналитика'],
  ['social', 'Маркетинг'], ['media', 'Медиатека'], ['knowledge', 'База знаний'],
  ['notifications', 'Уведомления'],
];
const more = ref(false);
watch(() => ui.view, (view) => {
  if (!primary.some(([key]) => key === view)) more.value = true;
}, { immediate: true });
</script>

<template>
  <aside class="sidebar">
    <a class="brand" href="#/dashboard" aria-label="BioTorf — главная">
      <span class="brand-mark" aria-hidden="true">🌱</span>
      <span><strong>BioTorf</strong><small>Рабочее пространство</small></span>
    </a>
    <nav class="nav main-nav" aria-label="Основные разделы">
      <button
        v-for="[key, icon, label] in primary" :key="key" type="button"
        :class="{ active: ui.view === key }" :aria-current="ui.view === key ? 'page' : undefined"
        @click="ui.go(key)"
      >
        <b aria-hidden="true">{{ icon }}</b>{{ label }}
      </button>
      <button class="more-button" type="button" aria-controls="extra-nav" :aria-expanded="more" @click="more = !more">
        <b aria-hidden="true">{{ more ? '−' : '＋' }}</b>Ещё
      </button>
    </nav>
    <nav v-if="more" id="extra-nav" class="nav extra-nav" aria-label="Дополнительные разделы">
      <button v-for="[key, label] in extra" :key="key" type="button" :class="{ active: ui.view === key }" @click="ui.go(key)">{{ label }}</button>
      <button v-if="ui.role === 'director'" type="button" :class="{ active: ui.view === 'employees' }" @click="ui.go('employees')">Сотрудники и роли</button>
      <button v-if="['director', 'operations'].includes(ui.role)" type="button" :class="{ active: ui.view === 'channels' }" @click="ui.go('channels')">Каналы связи</button>
      <a class="manual-entry" href="/manual.html#start" target="_blank" rel="noopener">Справка</a>
    </nav>
  </aside>
</template>

<style scoped>
.brand { text-decoration: none; color: inherit; }
.brand small { letter-spacing: normal; font-size: 11px; }
.main-nav { margin-top: 14px; }
.nav button { white-space: nowrap; }
.more-button { margin-top: 8px; }
.extra-nav { margin-top: 5px; padding-top: 6px; border-top: 1px solid #e4ebe6; }
.extra-nav button, .manual-entry { font-size: 13px; padding-inline-start: 45px; }
.manual-entry { display: block; padding-block: 9px; text-decoration: none; }
@media(max-width: 750px) {
  .main-nav, .extra-nav { margin-top: 5px; }
  .extra-nav button, .manual-entry { padding-inline: 8px; white-space: nowrap; }
}
</style>
