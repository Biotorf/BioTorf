<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useUiStore } from '@/stores/ui';
import TrainingExercise from './TrainingExercise.vue';
import { trainingCourses } from './steps';

const emit = defineEmits(['close']);
const ui = useUiStore();
const panel = ref(null);
const heading = ref(null);
const area = ref(null);
const position = ref(null);
const fallbackUsed = ref(false);
const storageKey = 'biotorf.training.v2:' + (ui.login || 'default');

function readProgress() {
  try {
    const data = JSON.parse(localStorage.getItem(storageKey) || '{}');
    return Object.fromEntries(trainingCourses.flatMap((course) => {
      const entry = data?.[course.id];
      return Number.isInteger(entry?.index) && entry.index >= 0 && entry.index < course.steps.length
        ? [[course.id, { index: entry.index, completed: entry.completed === true }]]
        : [];
    }));
  } catch {
    return {};
  }
}

const progress = ref(readProgress());
const courseId = ref('');
const index = ref(0);
const finished = ref(false);
const solved = ref(false);
const course = computed(() => trainingCourses.find((item) => item.id === courseId.value));
const step = computed(() => finished.value ? null : course.value?.steps[index.value] || null);
const isLast = computed(() => index.value === course.value?.steps.length - 1);
const completedCount = computed(() => Object.values(progress.value).filter((entry) => entry.completed).length);
const nextCourse = computed(() => trainingCourses.find((item) => !progress.value[item.id]?.completed));
const russianNumbers = new Intl.PluralRules('ru');
const stepLabels = { one: 'шаг', few: 'шага', many: 'шагов', other: 'шагов' };

let observer;
let resizeObserver;
let watchedTarget = null;
let fallbackTimer;
let measureFrame;
let allowFallback = false;
let running = false;
let previousOverflow;
let generation = 0;

function writeProgress(completed = progress.value[courseId.value]?.completed === true) {
  progress.value[courseId.value] = { index: index.value, completed };
  try {
    localStorage.setItem(storageKey, JSON.stringify(progress.value));
  } catch { /* Courses remain available if storage is disabled. */ }
}

function launch(item) {
  const previous = progress.value[item.id];
  courseId.value = item.id;
  index.value = previous?.completed ? 0 : previous?.index || 0;
  finished.value = false;
}

function showCourses() {
  courseId.value = '';
  finished.value = false;
}

function advance() {
  if (isLast.value) {
    writeProgress(true);
    finished.value = true;
  } else {
    index.value += 1;
  }
}

function close() {
  emit('close');
}

function targetWithName(name) {
  const candidates = document.querySelectorAll('[data-tour="' + name + '"]');
  for (const element of candidates) {
    if (element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden') return element;
  }
  return null;
}

function clearSpotlight() {
  clearTimeout(fallbackTimer);
  if (watchedTarget) resizeObserver?.unobserve(watchedTarget);
  watchedTarget = null;
  allowFallback = false;
  fallbackUsed.value = false;
  area.value = null;
  position.value = null;
}

function measure() {
  measureFrame = undefined;
  if (!step.value?.target || !panel.value) return;
  const primary = targetWithName(step.value.target);
  const fallbacks = [].concat(step.value.fallback || []);
  const element = primary || (allowFallback && fallbacks.map(targetWithName).find(Boolean)) || null;
  fallbackUsed.value = allowFallback && !primary;
  if (watchedTarget !== element) {
    if (watchedTarget) resizeObserver?.unobserve(watchedTarget);
    watchedTarget = element;
    if (element) {
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
  if (!rect || right <= left || bottom <= top) {
    area.value = null;
    position.value = null;
    return;
  }
  area.value = { left: left + 'px', top: top + 'px', width: right - left + 'px', height: bottom - top + 'px' };

  const dialog = panel.value.getBoundingClientRect();
  const gutter = 12;
  const center = (left + right - dialog.width) / 2;
  const bottomOfPanel = viewportHeight - dialog.height - gutter;
  const x = Math.max(gutter, Math.min(viewportWidth - dialog.width - gutter, center));
  const above = top - dialog.height - gutter;
  const below = bottom + gutter;
  const preferredY = below <= bottomOfPanel ? below : above >= gutter ? above
    : viewportHeight - bottom >= top ? bottomOfPanel : gutter;
  position.value = { left: x + 'px', top: Math.max(gutter, preferredY) + 'px' };
}

function scheduleMeasure() {
  if (running && step.value?.target && measureFrame == null) measureFrame = requestAnimationFrame(measure);
}

function stepMatchesRoute(current) {
  const [view, query] = location.hash.replace(/^#\/?/, '').split('?');
  if ((view || 'dashboard') !== current.view) return false;
  const params = new URLSearchParams(query);
  if (current.view === 'crm' && params.has('client')) return false;
  return Object.entries(current.params || {}).every(([key, value]) => params.get(key) === value);
}

watch([courseId, step], async ([, current]) => {
  const thisGeneration = ++generation;
  solved.value = false;
  clearSpotlight();
  if (current) {
    writeProgress();
    if (current.view && !stepMatchesRoute(current)) ui.go(current.view, current.params);
  }
  await nextTick();
  if (!running || thisGeneration !== generation) return;
  if (panel.value) panel.value.scrollTop = 0;
  heading.value?.focus({ preventScroll: true });
  if (!current?.target) return;
  scheduleMeasure();
  fallbackTimer = window.setTimeout(() => {
    allowFallback = true;
    scheduleMeasure();
  }, 250);
}, { flush: 'post' });

function handleRouteChange() {
  if (step.value?.view && !stepMatchesRoute(step.value)) close();
  else scheduleMeasure();
}

function handleKeys(event) {
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    close();
  }
  if (event.key !== 'Tab' || !panel.value) return;
  const focusable = [...panel.value.querySelectorAll('button, a[href], input, select, textarea')]
    .filter((control) => !control.matches(':disabled') && control.getClientRects().length);
  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && (document.activeElement === first || !focusable.includes(document.activeElement))) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && (document.activeElement === last || !focusable.includes(document.activeElement))) {
    event.preventDefault();
    first?.focus();
  }
}

onMounted(() => {
  running = true;
  previousOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';
  observer = new MutationObserver(scheduleMeasure);
  const main = document.querySelector('.shell');
  if (main) observer.observe(main, { childList: true, subtree: true });
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(scheduleMeasure);
    if (panel.value) resizeObserver.observe(panel.value);
  }
  addEventListener('resize', scheduleMeasure);
  addEventListener('scroll', scheduleMeasure, true);
  addEventListener('hashchange', handleRouteChange);
  addEventListener('keydown', handleKeys, true);
  panel.value?.focus({ preventScroll: true });
});

onBeforeUnmount(() => {
  running = false;
  clearSpotlight();
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
      <section ref="panel" class="training-card"
        :class="{ centered: !position, academy: !course, practice: step?.exercise, 'course-finish': finished }"
        :style="position" role="dialog" aria-modal="true" aria-labelledby="training-title" tabindex="-1">
        <template v-if="!course">
          <header class="academy-head">
            <div class="academy-intro">
              <h2 id="training-title" ref="heading" tabindex="-1">Обучение работе в CRM</h2>
              <p>Выберите рабочий сценарий. Мы подсветим нужные кнопки, а потренироваться можно на примерах внутри курса.</p>
            </div>
            <button type="button" class="training-close" aria-label="Закрыть обучение" @click="close">×</button>
          </header>

          <div class="academy-progress">
            <span>Пройдено курсов {{ completedCount }} из {{ trainingCourses.length }}</span>
            <progress :value="completedCount" :max="trainingCourses.length" aria-label="Пройденные курсы" />
          </div>
          <ul class="course-grid" aria-label="Учебные курсы">
            <li v-for="item in trainingCourses" :key="item.id" class="course-tile" :class="item.accent">
              <div class="course-meta">
                <span class="course-icon" aria-hidden="true">{{ item.icon }}</span>
                <span v-if="progress[item.id]?.completed" class="course-completed">✓ Пройден</span>
                <span v-else-if="progress[item.id]" class="course-length">Шаг {{ progress[item.id].index + 1 }} из {{ item.steps.length }}</span>
                <span v-else class="course-length">{{ item.steps.length }} {{ stepLabels[russianNumbers.select(item.steps.length)] }}</span>
              </div>
              <h3>{{ item.title }}</h3>
              <p>{{ item.description }}</p>
              <button type="button" class="btn" :class="{ primary: item.id === nextCourse?.id }"
                :aria-label="`${progress[item.id]?.completed ? 'Повторить курс' : progress[item.id] ? 'Продолжить курс' : 'Начать курс'} «${item.title}»`"
                @click="launch(item)">
                {{ progress[item.id]?.completed ? 'Повторить курс' : progress[item.id] ? 'Продолжить курс' : 'Начать курс' }}
                <span aria-hidden="true"> →</span>
              </button>
            </li>
          </ul>
          <footer class="academy-links">
            <a href="/manual.html#start" target="_blank" rel="noopener">Открыть текстовую инструкцию</a>
            <span>Прогресс сохраняется в этом браузере.</span>
          </footer>
        </template>

        <template v-else-if="finished">
          <header class="training-header">
            <span class="course-completed">✓ Курс пройден</span>
            <button type="button" class="training-close" aria-label="Закрыть обучение" @click="close">×</button>
          </header>
          <h2 id="training-title" ref="heading" tabindex="-1">{{ course.title }}</h2>
          <ul class="takeaways">
            <li v-for="item in course.takeaways" :key="item">{{ item }}</li>
          </ul>
          <a class="training-manual" :href="`/manual.html#${course.manual}`" target="_blank" rel="noopener">Открыть инструкцию по теме</a>
          <footer class="training-controls">
            <button type="button" class="btn ghost" @click="showCourses">Все курсы</button>
            <button v-if="nextCourse" type="button" class="btn primary" @click="launch(nextCourse)">Следующий курс</button>
            <button v-else type="button" class="btn primary" @click="close">Закрыть обучение</button>
          </footer>
        </template>

        <template v-else>
          <header class="training-header">
            <button type="button" class="training-back" @click="showCourses">‹ Все курсы</button>
            <span class="step-counter" aria-live="polite">Шаг {{ index + 1 }} из {{ course.steps.length }}</span>
            <button type="button" class="training-close" aria-label="Закрыть обучение" @click="close">×</button>
          </header>
          <progress :value="index + 1" :max="course.steps.length" aria-label="Прогресс курса" />
          <div class="step-context">
            <p class="step-label">{{ step.label }}</p>
            <button v-if="step.view" type="button" class="training-return" @click="close">Выйти и попробовать</button>
          </div>
          <h2 id="training-title" ref="heading" tabindex="-1">{{ step.title }}</h2>
          <template v-if="step.exercise">
            <p class="training-hint">Учебное задание. Рабочие записи здесь не меняются.</p>
            <TrainingExercise :key="`${course.id}:${index}`" :exercise="step.exercise" @solved="solved = true" />
          </template>
          <template v-else>
            <p class="step-intro">{{ step.text }}</p>
            <ol class="step-actions">
              <li v-for="action in step.actions" :key="action">{{ action }}</li>
            </ol>
            <p v-if="fallbackUsed && step.hint" class="training-hint">{{ step.hint }}</p>
          </template>
          <footer class="training-controls">
            <button v-if="index > 0" type="button" class="btn ghost" @click="index -= 1">Назад</button>
            <div class="training-paging">
              <button v-if="step.exercise && !solved" type="button" class="btn ghost" @click="advance">Пропустить задание</button>
              <button v-else type="button" class="btn primary" @click="advance">{{ isLast ? 'Завершить курс' : 'Далее' }} <span aria-hidden="true">→</span></button>
            </div>
          </footer>
        </template>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.training-layer { position: fixed; inset: 0; z-index: 500; }
.training-layer.without-target { background: rgb(9 30 23 / 59%); }
.training-spot {
  position: fixed;
  box-shadow: 0 0 0 150vmax rgb(9 30 23 / 59%);
  outline: 3px solid #78e7a9;
  border-radius: 12px;
  pointer-events: none;
}
.training-card {
  position: fixed;
  z-index: 1;
  max-height: calc(100dvh - 24px);
  width: min(435px, calc(100% - 24px));
  overflow: auto;
  touch-action: pan-y;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding: 14px 16px 16px;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: var(--panel);
  color: var(--ink);
  box-shadow: 0 18px 60px rgb(0 20 12 / 33%);
}
.training-card:focus, .training-card h2:focus { outline: none; }
.training-card.centered { top: 50%; left: 50%; transform: translate(-50%, -50%); }
.practice, .course-finish { width: min(485px, calc(100% - 24px)); }
.academy { width: min(810px, calc(100% - 24px)); padding: 20px; }
.academy-head { position: relative; }
.academy-intro {
  padding: 23px 54px 23px 22px;
  border: 1px solid var(--border);
  border-radius: 13px;
  background: linear-gradient(115deg, var(--accent-soft, var(--mint)), var(--surface-soft, var(--bg)));
  color: var(--ink);
}
.academy-head .training-close { position: absolute; top: 10px; right: 10px; }
.training-card h2 { margin: 0 0 8px; font-size: 21px; line-height: 1.15; overflow-wrap: anywhere; }
.academy h2 { margin-bottom: 8px; font-size: clamp(24px, 5vw, 36px); letter-spacing: -.035em; }
.training-card p { overflow-wrap: anywhere; }
.academy-intro p { margin: 0; max-width: 525px; line-height: 1.5; color: var(--ink); }
.academy-progress { display: flex; gap: 14px; align-items: center; margin: 14px 0; font-size: 13px; font-weight: 700; }
.academy-progress span { white-space: nowrap; }
.training-card progress { display: block; height: 6px; width: 100%; border: 0; border-radius: 10px; accent-color: var(--green); }
.training-card > progress { margin: 5px 0 12px; }
.course-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 0; margin: 0; list-style: none; }
.course-tile { display: flex; flex-direction: column; padding: 13px; gap: 7px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-soft, var(--bg)); }
.course-meta { display: flex; align-items: center; justify-content: space-between; gap: 5px; }
.course-icon { display: grid; width: 32px; height: 32px; place-items: center; border-radius: 9px; background: var(--course-tint, var(--accent-soft, var(--mint))); color: var(--course-ink, var(--accent-ink, var(--green))); font-size: 20px; font-weight: 800; }
.course-tile.blue { --course-tint: #e3f0fb; --course-ink: #1a4d80; }
.course-tile.amber { --course-tint: #faedcd; --course-ink: #75450a; }
.course-tile.plum { --course-tint: #f0e6f6; --course-ink: #754283; }
:global(html[data-theme='dark']) .course-tile.blue { --course-tint: #253c51; --course-ink: #b4d7f5; }
:global(html[data-theme='dark']) .course-tile.amber { --course-tint: #493a20; --course-ink: #f4d293; }
:global(html[data-theme='dark']) .course-tile.plum { --course-tint: #45324e; --course-ink: #edd0f9; }
.course-length, .course-completed { font-size: 12px; font-weight: 700; }
.course-length { color: var(--muted); }
.course-completed { color: var(--accent-ink, var(--green)); }
.course-tile h3 { margin: 0; font-size: 16px; line-height: 1.28; }
.course-tile p { margin: 0 0 6px; color: var(--muted); font-size: 13px; line-height: 1.4; }
.course-tile .btn { min-height: 38px; align-self: flex-start; margin-top: auto; }
.academy-links { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 14px; justify-content: space-between; margin-top: 14px; font-size: 12px; color: var(--muted); }
.academy-links a, .training-manual { color: var(--accent-ink, var(--green)); text-decoration: underline; }
.training-header, .training-controls, .training-paging { display: flex; align-items: center; gap: 8px; }
.training-header { justify-content: space-between; margin-bottom: 5px; }
.step-counter { color: var(--muted); font-size: 12px; font-weight: 700; }
.training-close, .training-back {
  background: var(--surface-soft, var(--bg));
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--ink);
  cursor: pointer;
  min-height: 36px;
}
.training-close { padding: 0; font-size: 26px; line-height: 1; width: 36px; flex: 0 0 auto; }
.training-back { padding: 4px 9px; font: inherit; font-size: 13px; font-weight: 650; }
.training-close:hover, .training-back:hover { border-color: var(--green); }
.step-context { display: flex; justify-content: space-between; align-items: center; gap: 6px; margin: 0 0 5px; }
.step-label { color: var(--accent-ink, var(--green)); font-size: 12px; font-weight: 750; margin: 0; }
.training-return { padding: 1px 0; border: 0; border-radius: 3px; background: transparent; color: var(--accent-ink, var(--green)); text-decoration: underline; font: inherit; font-size: 12px; cursor: pointer; }
.step-intro { margin: 0 0 10px; line-height: 1.42; }
.step-actions, .takeaways { margin: 0; padding: 0; list-style: none; }
.step-actions { counter-reset: instruction; }
.step-actions li, .takeaways li { position: relative; padding-inline-start: 31px; margin: 8px 0; font-size: 13px; line-height: 1.44; }
.step-actions li::before, .takeaways li::before { position: absolute; top: 0; inset-inline-start: 0; display: grid; width: 22px; height: 22px; place-items: center; border-radius: 50%; background: var(--accent-soft, var(--mint)); color: var(--accent-ink, var(--green)); font-weight: 750; }
.step-actions li::before { counter-increment: instruction; content: counter(instruction); font-size: 12px; }
.takeaways li::before { content: '✓'; }
.training-hint { margin: 8px 0; color: var(--muted); font-size: 12px; line-height: 1.4; }
.training-manual { display: inline-block; margin-top: 10px; font-size: 13px; }
.training-controls { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); justify-content: space-between; }
.training-paging { margin-inline-start: auto; }
.training-controls button { min-height: 36px; }
@media (max-width: 500px) {
  .academy { padding: 12px; }
  .academy-intro { padding: 16px 48px 16px 13px; }
  .academy-intro p { font-size: 13px; }
  .course-tile { padding: 9px; }
  .course-tile h3 { font-size: 14px; }
  .course-tile .btn { padding-inline: 7px; font-size: 12px; }
}
@media (max-width: 350px) {
  .course-grid { grid-template-columns: 1fr; }
  .academy-progress { flex-wrap: wrap; gap: 5px; }
  .training-card { padding: 10px 12px; }
}
</style>
