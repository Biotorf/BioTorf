<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { crmPhotosApi } from '@/api/crmPhotosClient';

const props = defineProps({
  collection: { type: String, required: true },
  recordId: { type: [String, Number], required: true },
  coverId: { type: String, default: undefined },
  alt: { type: String, default: '' },
});

const container = ref(null);
const visible = ref(false);
const src = ref('');
let observer;

function clearImage() {
  if (src.value) URL.revokeObjectURL(src.value);
  src.value = '';
}

onMounted(() => {
  if (!window.IntersectionObserver) {
    visible.value = true;
    return;
  }
  observer = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) return;
    visible.value = true;
    observer.disconnect();
  }, { rootMargin: '160px' });
  observer.observe(container.value);
});

onBeforeUnmount(() => observer?.disconnect());

watch(() => [props.collection, props.recordId, props.coverId, visible.value], async ([collection, recordId, knownId, inView], _, onCleanup) => {
  if (!inView || recordId == null || recordId === '' || knownId === '') return;
  const controller = new AbortController();
  const { signal } = controller;
  onCleanup(() => { controller.abort(); clearImage(); });
  try {
    let id = knownId;
    if (id === undefined) {
      const { items } = await crmPhotosApi.list(collection, recordId, { signal });
      id = items.find((photo) => photo.isCover)?.id || items[0]?.id;
    }
    if (!id) return;
    const blob = await crmPhotosApi.asset(collection, recordId, id, { signal, thumbnail: true });
    if (!signal.aborted) src.value = URL.createObjectURL(blob);
  } catch { /* фотографии скрыты или недоступны: оставляем обычный значок */ }
}, { immediate: true });
</script>

<template>
  <span ref="container" class="crm-thumbnail">
    <img v-if="src" :src="src" :alt="alt" decoding="async" @error="clearImage" />
    <slot v-else name="fallback">
      <svg class="placeholder" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="3" />
        <path d="m3.5 16 4.7-4.7 4 4 3-3 5.3 5.3" />
        <circle cx="15.5" cy="8.5" r="1.3" />
      </svg>
    </slot>
  </span>
</template>

<style scoped>
.crm-thumbnail {
  display: grid;
  place-items: center;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  min-width: 0;
  border-radius: inherit;
  color: var(--green);
  background: var(--accent-soft, var(--mint));
}
.crm-thumbnail img { display: block; width: 100%; height: 100%; min-height: 0; object-fit: cover; }
.placeholder { width: 35%; min-width: 18px; max-width: 42px; stroke: currentColor; stroke-width: 1.5; }
</style>
