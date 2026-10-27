<script setup>
import { useUiStore } from '@/stores/ui';
import { useDbStore } from '@/stores/db';
import { usePermissions } from '@/composables/usePermissions';

const ui = useUiStore();
const db = useDbStore();
const { ROLES } = usePermissions();
</script>

<template>
  <div class="topbar">
    <div class="search">
      <span>⌕</span>
      <input
        v-model="ui.search"
        type="search"
        placeholder="Поиск по текущему разделу…"
      />
    </div>
    <div class="topright">
      <button class="toolbar-icon" @click="ui.go('comms')" title="Коммуникации: звонки и сообщения">
        ☎<i v-if="db.comms.filter((c) => !c.read).length">{{ db.comms.filter((c) => !c.read).length }}</i>
      </button>
      <button class="toolbar-icon" @click="ui.go('notifications')" title="Уведомления">
        ♢<i>{{ db.lateTasks.length }}</i>
      </button>
      <button class="toolbar-icon" @click="ui.go('calendar')" title="Календарь">▦</button>
      <span class="role" :title="ui.login ? `Вход: ${ui.login}` : 'Демо-режим (без бэкенда)'">
        {{ ROLES[ui.role] || ui.role }}
      </span>
    </div>
  </div>
</template>