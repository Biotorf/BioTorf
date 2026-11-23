<script setup>
import { onMounted, ref } from 'vue';
import { automationApi } from '@/api/automationClient';
import { useUiStore } from '@/stores/ui';

const ui = useUiStore();
const rules = ref([]);
const activity = ref([]);
const canManage = ref(false);
const busy = ref(false);
const error = ref('');
const dictionary = {
  created: 'Задача создана', completed: 'Задача выполнена', canceled: 'Задача отменена',
  rescheduled: 'Срок обновлён', enabled: 'Правило включено', disabled: 'Правило выключено',
};
const dateTime = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
function formatTime(value) {
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? dateTime.format(parsed) : '';
}
async function run(action) {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const result = await action();
    rules.value = result.rules || [];
    activity.value = result.activity || [];
    canManage.value = result.canManage === true;
  } catch (cause) {
    error.value = cause.message || 'Не удалось загрузить правила.';
  } finally {
    busy.value = false;
  }
}
onMounted(() => run(automationApi.list));
</script>

<template>
  <section class="automation">
    <header class="pagehead">
      <div>
        <h1>Автоматизация</h1>
        <p class="subtitle">Правила, которые срабатывают при изменении записей CRM.</p>
      </div>
      <button type="button" class="btn" :disabled="busy" @click="run(automationApi.list)">Обновить</button>
    </header>
    <p v-if="error" class="danger-text" role="alert">{{ error }}</p>
    <p v-else-if="busy && !rules.length" role="status">Загрузка правил…</p>
    <section v-for="rule in rules" :key="rule.id" class="panel rule">
      <div>
        <h2>{{ rule.title }}</h2>
        <p>{{ rule.description }}</p>
      </div>
      <div class="rule-controls">
        <span class="pill" :class="{ gray: !rule.enabled }">{{ rule.enabled ? 'Включено' : 'Выключено' }}</span>
        <button v-if="canManage" type="button" class="btn slim" :disabled="busy" @click="run(() => automationApi.update(rule.id, !rule.enabled))">
          {{ rule.enabled ? 'Выключить' : 'Включить' }}
        </button>
      </div>
    </section>
    <section v-if="rules.length" class="panel history">
      <h2>История выполнения</h2>
      <p v-if="!activity.length" class="subtitle">Срабатываний пока нет.</p>
      <ul v-else>
        <li v-for="(row, index) in activity" :key="row.id || row.at + '-' + index">
          <div>
            <strong>{{ dictionary[row.action] || row.action }}</strong>
            <small>{{ [formatTime(row.at), row.actor].filter(Boolean).join(' · ') }}</small>
          </div>
          <button v-if="row.taskId" type="button" class="btn slim ghost" @click="ui.openRecord('task', row.taskId)">Открыть задачу</button>
        </li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.automation { max-width: 960px; }
.rule, .rule-controls, .history li { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.rule p { margin: 6px 0 0; color: #4f675d; }
.rule + .rule, .history { margin-top: 12px; }
.history h2 { margin-bottom: 8px; }
.history ul { list-style: none; padding: 0; margin: 0; }
.history li + li { border-top: 1px solid #e6ede9; }
.history li { padding: 8px 0; }
.history small { display: block; color: #4f675d; }
</style>
