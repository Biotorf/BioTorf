<script setup>
import { computed } from 'vue';
import { useUiStore } from '@/stores/ui';
import MiniProfile from '@/components/auth/MiniProfile.vue';

const ui = useUiStore();
const searchable = computed(() => ['orders', 'pipeline', 'pilots'].includes(ui.view));
</script>

<template>
  <header class="topbar">
    <label v-if="searchable" class="search">
      <span aria-hidden="true">⌕</span>
      <input v-model="ui.search" type="search" aria-label="Поиск по разделу" placeholder="Поиск по разделу" />
    </label>
    <div class="topright profile"><MiniProfile /></div>
  </header>
</template>

<style scoped>
.topbar { min-height: 56px; height: auto; padding-block: 7px; }
.profile { margin-inline-start: auto; }
</style>
