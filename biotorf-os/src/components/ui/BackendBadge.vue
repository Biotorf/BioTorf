<script setup>
// Бейдж статуса привязки раздела к бэкенду:
// «Привязано к бекенду» — когда сервер доступен (db.serverOnline),
// иначе — подсказка, что раздел работает на локальном демо-состоянии.
import { computed } from 'vue';
import { useDbStore } from '@/stores/db';

const props = defineProps({ collection: { type: String, default: null } });
const db = useDbStore();

const online = computed(() => {
  if (!db.serverOnline) return false;
  // если указана коллекция и она пуста при живом сервере — скорее всего данные ещё не загружены
  if (props.collection) return (db.data[props.collection] || []).length > 0;
  return true;
});
</script>

<template>
  <span v-if="online" class="chip backend-chip">🟢 Привязано к бекенду</span>
  <span v-else class="chip neutral" title="Сервер недоступен или данных ещё нет — показывается локальное демо-состояние">Демо-режим (локально)</span>
</template>

<style scoped>
.backend-chip { background: #e5f5ee; color: #137d60; }
</style>
