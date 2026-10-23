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
      <button class="toolbar-icon" @click="ui.go('notifications')" title="Уведомления">
        ♢<i>{{ db.lateTasks.length }}</i>
      </button>
      <button class="toolbar-icon" @click="ui.go('calendar')" title="Календарь">▦</button>
      <select v-model="ui.role" class="role">
        <option v-for="(label, key) in ROLES" :key="key" :value="key">{{ label }}</option>
      </select>
    </div>
  </div>
</template>