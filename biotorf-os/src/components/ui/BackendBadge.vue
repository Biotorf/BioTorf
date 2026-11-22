<script setup>
// Компактный индикатор привязки раздела к бэкенду (без надписей «демо-режим»):
// зелёная точка — данные с сервера; серая — сервер пока недоступен (показывается локальное состояние).
import { computed } from 'vue';
import { useDbStore } from '@/stores/db';

const props = defineProps({ collection: { type: String, default: null } });
const db = useDbStore();

const online = computed(() => !!db.serverOnline);
const syncing = computed(() => db.crmSyncError);

async function retry() {
  try {
    await db.retryCrmSync();
  } catch { /* the error stays visible */ }
}

function reload() {
  if (confirm('Загрузить данные с сервера и удалить несинхронизированные изменения CRM в этом браузере?')) {
    db.pullCrmState({ discardPending: true });
  }
}
</script>

<template>
  <span
    class="dot"
    :class="online ? 'on' : 'off'"
    :title="online ? 'Раздел привязан к серверу' : 'Сервер временно недоступен — показаны локальные данные'"
  ></span>
  <span v-if="syncing" class="sync-error" role="status">
    {{ syncing }}
    <button type="button" class="btn slim ghost" @click="retry">Повторить синхронизацию</button>
    <button v-if="syncing.startsWith('CRM API 409')" type="button" class="btn slim ghost" @click="reload">Загрузить версию сервера</button>
  </span>
</template>

<style scoped>
.dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  vertical-align: middle;
}
.dot.on { background: #27b95a; box-shadow: 0 0 0 3px rgba(39, 185, 90, 0.18); }
.dot.off { background: #c3cec8; }
.sync-error { color: #8a4610; font-size: 12px; }
</style>
