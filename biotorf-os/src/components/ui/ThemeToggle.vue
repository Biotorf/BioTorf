<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';

const dark = ref(document.documentElement.dataset.theme === 'dark');
function update({ detail }) { dark.value = detail === 'dark'; }
function toggle() {
  window.dispatchEvent(new CustomEvent('biotorf:set-theme', { detail: dark.value ? 'light' : 'dark' }));
}
onMounted(() => window.addEventListener('biotorf:theme-changed', update));
onBeforeUnmount(() => window.removeEventListener('biotorf:theme-changed', update));
</script>

<template>
  <button type="button" class="btn slim theme-toggle" role="switch" aria-label="Тёмная тема" :aria-checked="dark"
    :title="dark ? 'Включить светлую тему' : 'Включить тёмную тему'" data-tour="theme-switch" @click="toggle">
    <svg v-if="dark" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" aria-hidden="true">
      <path d="M20.6 15.1A9 9 0 0 1 8.9 3.4a9 9 0 1 0 11.7 11.7Z" stroke-linejoin="round" />
    </svg>
    <svg v-else viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42m0-14.14-1.42 1.42m-11.3 11.3-1.42 1.42" stroke-linecap="round" />
    </svg>
    <span>Тёмная тема</span>
  </button>
</template>

<style scoped>
.theme-toggle { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-width: 38px; min-height: 38px; white-space: nowrap; }
.theme-toggle[aria-checked="true"] { background: var(--accent-soft); border-color: var(--accent-border); color: var(--accent-ink); }
.theme-toggle svg { width: 18px; height: 18px; flex: none; }
@media (max-width: 940px) {
  .theme-toggle span { display: none; }
}
@media (max-width: 750px) {
  .theme-toggle { min-width: 44px; min-height: 44px; }
}
</style>
