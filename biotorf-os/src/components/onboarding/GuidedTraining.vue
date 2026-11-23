<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useUiStore } from '@/stores/ui';
import { trainingSteps } from './steps';

const emit = defineEmits(['close']);
const ui = useUiStore();
const panel = ref(null);
const area = ref(null);
const position = ref(null);
const fallbackUsed = ref(false);
const storageKey = 'biotorf.training.v1:' + (ui.login || 'default');

function readProgress() {
  try {
    const value = Number(localStorage.getItem(storageKey));
    if (Number.isInteger(value) && value >= 0 && value < trainingSteps.length) return value;
  } catch { /* Storage may be disabled. */ }
  return 0;
}

const index = ref(readProgress());
const step = computed(() => trainingSteps[index.value]);
const last = computed(() => index.value === trainingSteps.length - 1);
let observer;
let resizeObserver;
let watchedTarget = null;
let fallbackTimer;
let measureFrame;
let allowFallback = false;
let running = false;
let previousOverflow;
let generation = 0;

function writeProgress(value) {
  try {
    if (value === null) localStorage.removeItem(storageKey);
    else localStorage.setItem(storageKey, String(value));
  } catch { /* Training still works without storage. */ }
}

function targetWithName(name) {
  if (!name) return null;
  const candidates = document.querySelectorAll('[data-tour="' + name + '"]');
  for (const element of candidates) {
    if (element.getClientRects().length &&
        getComputedStyle(element).visibility !== 'hidden') return element;
  }
  return null;
}

function measure() {
  measureFrame = undefined;
  const primary = targetWithName(step.value.target);
  const fallbacks = [].concat(step.value.fallback || []);
  const element = primary || (allowFallback && fallbacks.map(targetWithName).find(Boolean)) || null;
  fallbackUsed.value = allowFallback && !primary;
  if (watchedTarget !== element) {
    if (watchedTarget) resizeObserver?.unobserve(watchedTarget);
    watchedTarget = element;
    if (element) {
      // Center targets before measuring so the frame also works on small screens.
      element.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
      resizeObserver?.observe(element);
    }
  }

  const viewportWidth = document.documentElement.clientWidth;
  const viewportHeight = window.innerHeight;
  const rect = element?.getBoundingClientRect();
  const margin = 6;
  const left = Math.max(0, (rect?.left || 0) - margin);
  const right = Math.min(viewportWidth, (rect?.right || 0) + margin);
  const top = Math.max(0, (rect?.top || 0) - margin);
  const bottom = Math.min(viewportHeight, (rect?.bottom || 0) + margin);
  area.value = rect && right > left && bottom > top ? {
    left: left + 'px', top: top + 'px', width: right - left + 'px', height: bottom - top + 'px',
  } : null;

  if (!panel.value) return;
  const dialog = panel.value.getBoundingClientRect();
  const gutter = 12;
  if (!area.value) {
    position.value = null;
    return;
  }
  const center = (left + right - dialog.width) / 2;
  const x = Math.max(gutter, Math.min(viewportWidth - dialog.width - gutter, center));
  const above = top - dialog.height - gutter;
  const below = bottom + gutter;
  const freeAbove = top;
  const freeBelow = viewportHeight - bottom;
  const preferredY = below + dialog.height + gutter <= viewportHeight ? below
    : above >= gutter ? above
    : freeBelow >= freeAbove ? viewportHeight - dialog.height - gutter : gutter;
  position.value = { left: x + 'px', top: Math.max(gutter, preferredY) + 'px' };
}

function scheduleMeasure() {
  if (running && measureFrame == null) measureFrame = requestAnimationFrame(measure);
}

function atStep(current) {
  const [view, query] = location.hash.replace(/^#\/?/, '').split('?');
  // The dashboard can also be the default route without a hash.
  if ((view || 'dashboard') !== current.view) return false;
  const params = new URLSearchParams(query);
  if (current.view === 'crm' && params.has('client')) return false;
  return Object.entries(current.params || {}).every(([key, value]) => params.get(key) === value);
}

async function goToStep() {
  const thisGeneration = ++generation;
  const current = step.value;
  writeProgress(index.value);
  clearTimeout(fallbackTimer);
  fallbackUsed.value = false;
  allowFallback = false;
  if (watchedTarget) resizeObserver?.unobserve(watchedTarget);
  watchedTarget = null;
  area.value = null;
  position.value = null;
  if (!atStep(current)) ui.go(current.view, current.params);
  await nextTick();
  if (!running || thisGeneration !== generation) return;
  scheduleMeasure();
  // Async route and permission-dependent controls both have stable fallbacks.
  fallbackTimer = window.setTimeout(() => {
    allowFallback = true;
    scheduleMeasure();
  }, 250);
}

watch(index, goToStep, { flush: 'post' });

function close(completed = false) {
  if (completed) writeProgress(null);
  emit('close');
}

function handleRouteChange() {
  if (!atStep(step.value)) close();
  else scheduleMeasure();
}

function handleKeys(event) {
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    close();
  }
  if (event.key !== 'Tab' || !panel.value) return;

  const focusable = [...panel.value.querySelectorAll('button:not([disabled]), a[href]')];
  const first = focusable[0];
  const lastControl = focusable.at(-1);
  if (event.shiftKey && (document.activeElement === first || !focusable.includes(document.activeElement))) {
    event.preventDefault();
    lastControl?.focus();
  } else if (!event.shiftKey && (document.activeElement === lastControl || !focusable.includes(document.activeElement))) {
    event.preventDefault();
    first?.focus();
  }
}

onMounted(() => {
  running = true;
  previousOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';
  observer = new MutationObserver(scheduleMeasure);
  const content = document.querySelector('main .content');
  if (content) observer.observe(content, { childList: true, subtree: true });
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(scheduleMeasure);
    if (panel.value) resizeObserver.observe(panel.value);
  }
  addEventListener('resize', scheduleMeasure);
  addEventListener('scroll', scheduleMeasure, true);
  addEventListener('hashchange', handleRouteChange);
  addEventListener('keydown', handleKeys, true);
  goToStep();
  panel.value?.focus({ preventScroll: true });
});

onBeforeUnmount(() => {
  running = false;
  clearTimeout(fallbackTimer);
  if (measureFrame != null) cancelAnimationFrame(measureFrame);
  observer?.disconnect();
  resizeObserver?.disconnect();
  removeEventListener('resize', scheduleMeasure);
  removeEventListener('scroll', scheduleMeasure, true);
  removeEventListener('hashchange', handleRouteChange);
  removeEventListener('keydown', handleKeys, true);
  document.body.style.overflow = previousOverflow ?? '';
});
</script>

<template>
  <Teleport to="body">
    <div class="training-layer" :class="{ 'without-target': !area }">
      <div v-if="area" class="training-spot" :style="area" aria-hidden="true" />
      <section ref="panel" class="training-card" :class="{ centered: !position }" :style="position"
               role="dialog" aria-modal="true" aria-labelledby="training-title" tabindex="-1">
        <header class="training-header">
          <span aria-live="polite">Шаг {{ index + 1 }} из {{ trainingSteps.length }}</span>
          <button type="button" class="training-close" aria-label="Закрыть обучение" @click="close()">×</button>
        </header>
        <progress :value="index + 1" :max="trainingSteps.length" aria-label="Прогресс обучения" />
        <h2 id="training-title" aria-live="polite">{{ step.title }}</h2>
        <p>{{ step.text }}</p>
        <p v-if="fallbackUsed && step.hint" class="training-hint">{{ step.hint }}</p>
        <a v-if="index === 0 || last" class="training-manual" href="/manual.html#start" target="_blank" rel="noopener">Открыть текстовую инструкцию</a>
        <footer class="training-controls">
          <button v-if="index > 0" type="button" class="btn slim ghost" @click="index = 0">Сначала</button>
          <div class="training-paging">
            <button type="button" class="btn slim" :disabled="index === 0" @click="index -= 1">Назад</button>
            <button v-if="!last" type="button" class="btn primary slim" @click="index += 1">Далее</button>
            <button v-else type="button" class="btn primary slim" @click="close(true)">Завершить</button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.training-layer { position: fixed; inset: 0; z-index: 500; }
.training-layer.without-target { background: rgb(11 37 27 / 48%); }
.training-spot { position: fixed; box-shadow: 0 0 0 150vmax rgb(11 37 27 / 48%); outline: 2px solid #73dda4; border-radius: 10px; pointer-events: none; }
.training-card { position: fixed; z-index: 1; width: min(380px, calc(100% - 24px)); max-height: calc(100dvh - 24px); overflow: auto; touch-action: pan-y; overscroll-behavior: contain; padding: 13px 16px 15px; border: 1px solid #cde4d6; border-radius: 14px; background: white; color: #173b2d; box-shadow: 0 14px 46px rgb(15 48 35 / 28%); }
.training-card.centered { top: 50%; left: 50%; transform: translate(-50%, -50%); }
.training-header, .training-controls, .training-paging { display: flex; align-items: center; gap: 8px; }
.training-header { justify-content: space-between; color: #356750; font-size: 12px; font-weight: 700; }
.training-close { border: 0; border-radius: 8px; font-size: 23px; line-height: 1; color: #27573f; background: #eef7f1; width: 34px; height: 34px; }
.training-card progress { display: block; width: 100%; height: 5px; margin: 5px 0 11px; border: 0; border-radius: 8px; accent-color: #168148; }
.training-card h2 { font-size: 19px; margin: 0 0 6px; }
.training-card p { margin: 0 0 10px; line-height: 1.45; overflow-wrap: anywhere; }
.training-hint { color: #4f695c; font-size: 12px; }
.training-manual { display: inline-block; color: #176b51; font-size: 13px; margin-bottom: 10px; }
.training-controls { justify-content: space-between; }
.training-paging { margin-inline-start: auto; }
.training-controls button { min-height: 36px; }
.training-close:focus-visible, .training-controls button:focus-visible { outline: 2px solid #0c814b; outline-offset: 2px; }
</style>
