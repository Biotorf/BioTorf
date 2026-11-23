<script setup>
import { computed } from 'vue';
import { useUiStore } from '@/stores/ui';
import MiniProfile from '@/components/auth/MiniProfile.vue';

const emit = defineEmits(['start-training']);
const ui = useUiStore();
const navigation = [
  { name: 'Продажи', views: [['journey', 'Маршруты'], ['pipeline', 'Воронка'], ['orders', 'Заказы'], ['finance', 'Финансы']] },
  { name: 'Операции', views: [['shipments', 'Поставки и отгрузки'], ['production', 'Производство'], ['warehouse', 'Склад'], ['products', 'Каталог']] },
  { name: 'Задачи', views: [['tasks', 'Задачи'], ['calendar', 'Календарь'], ['automation', 'Автоматизация']] },
];
const section = computed(() => navigation.find((group) => group.views.some(([key]) => key === ui.view)));
const searchable = computed(() => ['orders', 'pilots'].includes(ui.view));
</script>

<template>
  <header class="topbar">
    <nav v-if="section" class="section-nav" :aria-label="section.name">
      <a v-for="[key, label] in section.views" :key="key" :href="'#/' + key"
         :aria-current="ui.view === key ? 'page' : undefined">{{ label }}</a>
    </nav>
    <label v-if="searchable" class="search">
      <span aria-hidden="true">⌕</span>
      <input v-model="ui.search" type="search" aria-label="Поиск по разделу" placeholder="Поиск по разделу" />
    </label>
    <div class="topright profile">
      <button type="button" class="btn slim training-trigger" @click="emit('start-training', $event)">Обучение</button>
      <MiniProfile />
    </div>
  </header>
</template>

<style scoped>
.topbar { min-height: 56px; height: auto; padding-block: 7px; gap: 10px; }
.profile { margin-inline-start: auto; }
.section-nav { min-width: 0; display: flex; align-items: center; gap: 4px; overflow-x: auto; }
.section-nav a { flex: none; font-size: 13px; color: #4b675b; text-decoration: none; padding: 7px 9px; border-radius: 7px; white-space: nowrap; }
.section-nav a:hover, .section-nav [aria-current="page"] { background: #ecf6ef; color: #145a43; }
.section-nav [aria-current="page"] { font-weight: 720; }
@media(max-width: 750px) {
  .section-nav { flex: 1 0 100%; order: 2; }
  .search { order: 3; }
}
</style>
