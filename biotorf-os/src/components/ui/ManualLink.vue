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
     title="Открыть книгу пользователя для этого раздела">
    📖 <span class="cap">Книга</span>
  </a>
</template>

<style scoped>
.manual-link{
  display:inline-flex;align-items:center;gap:6px;text-decoration:none;
  font-size:12.5px;font-weight:650;color:#214f37;background:#eef7f1;
  border:1px solid #cfe4d6;border-radius:9px;padding:6px 10px;cursor:pointer;
  transition:background .15s ease, box-shadow .15s ease;white-space:nowrap;
}
.manual-link:hover{background:#dff0e5;box-shadow:0 2px 8px rgba(33,79,55,.12)}
@media (max-width:900px){ .cap{display:none} }
</style>
