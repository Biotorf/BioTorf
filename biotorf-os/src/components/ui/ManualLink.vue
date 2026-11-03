<script setup>
// Кнопка-подсказка «📖 Книга пользователя»: открывает руководство
// (biotorf-os/public/manual.html) на нужной секции. Секция выбирается по
// текущему разделу приложения — см. карту VIEW_TO_SECTION ниже.
import { computed } from 'vue';
import { useUiStore } from '@/stores/ui';

const ui = useUiStore();

// раздел приложения → якорь главы в manual.html
const VIEW_TO_SECTION = {
  dashboard:   'start',
  crm:         'crm',
  comms:       'comms',
  pipeline:    'pipeline',
  journey:     'pipeline',
  pilots:      'pilots',
  orders:      'rules',
  shipments:   'logistics',
  tasks:       'tasks',
  calendar:    'regiment',
  products:    'products',
  production:  'warehouse',
  warehouse:   'warehouse',
  finance:     'quotes',
  analytics:   'analytics',
  knowledge:   'start',
  social:      'marketing',
  media:       'marketing',
  notifications: 'regiment',
  employees:   'roles',
};

const href = computed(() => `/manual.html#${VIEW_TO_SECTION[ui.view] || 'start'}`);
</script>

<template>
  <a class="manual-link" :href="href" target="_blank" rel="noopener"
     title="Открыть руководство для этого раздела">?</a>
</template>

<style scoped>
.manual-link{
  display:inline-grid;place-items:center;width:30px;height:30px;flex:none;
  border-radius:50%;text-decoration:none;cursor:pointer;
  font-size:14px;font-weight:800;color:#214f37;background:#eef7f1;
  border:1px solid #cfe4d6;
  transition:background .15s ease, box-shadow .15s ease, transform .15s ease;
}
.manual-link:hover{
  background:#dff0e5;box-shadow:0 2px 10px rgba(33,79,55,.18);transform:scale(1.08);
}
.manual-link:active{transform:scale(.94)}
@media (prefers-reduced-motion:reduce){
  .manual-link{transition:none}
  .manual-link:hover{transform:none}
}
</style>
