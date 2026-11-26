<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { departmentTasksApi } from '@/api/departmentTasksClient';

const db = useDbStore();
const departments = { production: 'Производство', marketing: 'Маркетинг', sales: 'Отдел продаж' };
const statuses = { new: 'К исполнению', working: 'В работе', blocked: 'Задержка', done: 'Выполнена', cancelled: 'Отменена' };
const closed = (task) => ['done', 'cancelled'].includes(task.status);
const dateFormat = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Asia/Bishkek', dateStyle: 'short', timeStyle: 'short', hourCycle: 'h23' });
const toDeadline = (value) => value + ':00+06:00';
const inputDate = (value) => new Date(Date.parse(value) + 6 * 3600 * 1000).toISOString().slice(0, 16);
const statusKeys = (task) => Object.keys(statuses).filter((key) => key !== 'cancelled' || task.canAssign);
const showDate = (value) => dateFormat.format(new Date(value));
const now = ref(Date.now());
const overdue = (task) => !closed(task) && Date.parse(task.deadline) < now.value;
const timer = setInterval(() => { now.value = Date.now(); }, 15000);
onUnmounted(() => clearInterval(timer));

const data = ref(null);
const active = ref('production');
const onlyOverdue = ref(false);
const editor = ref(null);
const busy = ref(false);
const error = ref('');
const message = ref('');
const staff = (department) => (data.value?.employees || []).filter((employee) => employee.active && employee.department === department);
const employeeName = (login) => data.value?.employees.find((employee) => employee.login === login)?.name || login || '—';
const products = computed(() => db.skus.filter((item) =>
  (/^(agro|home)$/i.test(String(item.line).trim()) || /\b(agro|home)\b/i.test(item.name || '')) && Number(String(item.pack).replace(',', '.')) > 0));
const totals = computed(() => (data.value?.items || []).filter((task) => task.department === active.value));
const rows = computed(() => totals.value.filter((task) => !onlyOverdue.value || overdue(task))
  .sort((a, b) => Number(closed(a)) - Number(closed(b)) || Date.parse(a.deadline) - Date.parse(b.deadline)));
const lateCount = computed(() => totals.value.filter(overdue).length);
let itemKey = 0;

function emptyLine() { return { key: ++itemKey, productId: '', quantity: 1 }; }

async function load() {
  data.value = await departmentTasksApi.list();
  if (!data.value.canCreate && !data.value.items.some((task) => task.department === active.value)) {
    active.value = data.value.items[0]?.department || active.value;
  }
}

async function refresh() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try { await load(); } catch (cause) { error.value = cause.message; }
  finally { busy.value = false; }
}
onMounted(refresh);

function openCreate() {
  error.value = '';
  message.value = '';
  editor.value = { department: active.value, title: '', description: '', coordinator: '', deadline: '', items: [emptyLine()] };
}
function openEdit(task) {
  error.value = '';
  message.value = '';
  editor.value = {
    task, assignee: task.assignee || '', deadline: inputDate(task.deadline), status: task.status,
    progress: task.progress, note: task.note, completed: Object.fromEntries(task.items.map((item) => [item.productId, item.completed])),
  };
}
function selectDepartment(key) {
  active.value = key;
  onlyOverdue.value = false;
  editor.value = null;
  error.value = '';
  message.value = '';
}

async function save() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  const form = editor.value;
  try {
    if (!form.task) {
      const { department, title, description, coordinator, deadline, items } = form;
      await departmentTasksApi.create({
        department, title: title.trim(), description, coordinator, deadline: toDeadline(deadline),
        items: department === 'production' ? items.map(({ productId, quantity }) => ({ productId, quantity })) : [],
      });
      message.value = 'Задача передана в отдел.';
    } else {
      const { task, assignee, deadline, status, progress, completed, note } = form;
      const changes = { revision: task._updatedAt, status, note };
      if (task.canAssign && assignee && assignee !== task.assignee) changes.assignee = assignee;
      if (task.canAssign && deadline !== inputDate(task.deadline)) changes.deadline = toDeadline(deadline);
      if (task.items.length) changes.completed = completed;
      else changes.progress = progress;
      await departmentTasksApi.update(task.id, changes);
      message.value = 'Задача обновлена.';
    }
    editor.value = null;
    await load();
  } catch (cause) {
    error.value = cause.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="panel department-tasks" aria-labelledby="department-title">
    <header class="section-header">
      <div>
        <h2 id="department-title">Задачи отделов</h2>
        <p class="subtitle">Сроки указаны по Бишкеку (UTC+6)</p>
      </div>
      <div class="actionbar">
        <button type="button" class="btn slim" :disabled="busy" @click="refresh">Обновить</button>
        <button v-if="data?.canCreate" type="button" class="btn primary slim" :disabled="busy" @click="openCreate">Поставить задачу отделу</button>
      </div>
    </header>
    <p v-if="error" class="danger-text" role="alert">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <template v-if="data">
      <nav class="actionbar" aria-label="Отделы">
        <button v-for="(label, key) in departments" :key="key" type="button" class="btn slim"
          :class="{ primary: active === key }" :aria-pressed="active === key" :disabled="busy"
          @click="selectDepartment(key)">{{ label }}</button>
      </nav>

      <form v-if="editor" class="task-editor" @submit.prevent="save">
        <h3>{{ editor.task ? editor.task.title : 'Новое поручение · ' + departments[editor.department] }}</h3>
        <p v-if="editor.task?.description">{{ editor.task.description }}</p>
        <fieldset :disabled="busy || !!(editor.task && closed(editor.task))">
          <template v-if="!editor.task">
            <div class="task-fields">
              <label class="field">Название задачи <input v-model="editor.title" class="input" required maxlength="200" /></label>
              <label class="field">Ответственный от отдела
                <select v-model="editor.coordinator" class="select" required>
                  <option value="" disabled>Выберите сотрудника</option>
                  <option v-for="person in staff(editor.department)" :key="person.login" :value="person.login">{{ person.name }}</option>
                </select>
              </label>
            </div>
            <p v-if="!staff(editor.department).length" class="mini">В отделе пока нет активных сотрудников с подходящей ролью.</p>
            <label class="field">Что нужно сделать <textarea v-model="editor.description" class="textarea" maxlength="4000" rows="2" /></label>
          </template>
          <div class="task-fields">
            <label v-if="!editor.task || editor.task.canAssign" class="field">Срок исполнения (дата и время)
              <input v-model="editor.deadline" type="datetime-local" class="input" required />
            </label>
            <label v-if="editor.task?.canAssign" class="field">Исполнитель
              <select v-model="editor.assignee" class="select">
                <option value="" disabled>Выберите сотрудника отдела</option>
                <option v-for="person in staff(editor.task.department)" :key="person.login" :value="person.login">{{ person.name }}</option>
              </select>
            </label>
            <label v-if="editor.task" class="field">Статус
              <select v-model="editor.status" class="select" aria-label="Статус">
                <option v-for="key in statusKeys(editor.task)" :key="key" :value="key">{{ statuses[key] }}</option>
              </select>
            </label>
            <label v-if="editor.task && !editor.task.items.length" class="field">Готовность, %
              <input v-model.number="editor.progress" type="number" min="0" max="100" step="1" class="input" required />
            </label>
          </div>
          <template v-if="!editor.task && editor.department === 'production'">
            <h4>План выпуска</h4>
            <p class="mini">Выберите Agro или Home нужной фасовки из каталога. Количество указывайте в канистрах или бутылках.</p>
            <div v-for="(item, index) in editor.items" :key="item.key" class="task-fields">
              <label class="field">Товар и фасовка
                <select v-model="item.productId" class="select" required>
                  <option value="" disabled>Выберите товар</option>
                  <option v-for="product in products" :key="product.id" :value="product.id">{{ product.name }} · {{ product.pack }} л</option>
                </select>
              </label>
              <label class="field">Количество, шт. <input v-model.number="item.quantity" type="number" min="1" max="1000000000" step="1" class="input" required /></label>
              <button v-if="editor.items.length > 1" type="button" class="btn slim ghost" @click="editor.items.splice(index, 1)">Убрать позицию</button>
            </div>
            <button type="button" class="btn slim" :disabled="editor.items.length >= 50" @click="editor.items.push(emptyLine())">Добавить позицию</button>
          </template>
          <template v-if="editor.task?.items.length">
            <h4>Фактический выпуск</h4>
            <div class="task-fields">
              <label v-for="item in editor.task.items" :key="item.productId" class="field">
                {{ item.name }} · {{ item.pack }} л · план {{ item.quantity }} шт.
                <input v-model.number="editor.completed[item.productId]" type="number" min="0" :max="item.quantity" step="1" class="input" required />
              </label>
            </div>
          </template>
          <label v-if="editor.task" class="field">{{ editor.status === 'blocked' ? 'Причина задержки' : 'Комментарий о ходе работы' }}
            <textarea v-model="editor.note" class="textarea" :required="editor.status === 'blocked'" maxlength="2000" rows="2" />
          </label>
        </fieldset>
        <div class="actionbar">
          <button v-if="!editor.task || !closed(editor.task)" class="btn primary slim" :disabled="busy">Сохранить</button>
          <button type="button" class="btn slim" :disabled="busy" @click="editor = null">Закрыть</button>
        </div>
      </form>

      <div class="section-header totals">
        <span>Всего {{ totals.length }} · Просрочено {{ lateCount }}</span>
        <label><input v-model="onlyOverdue" type="checkbox" /> Только просроченные</label>
      </div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Задача</th><th>Ответственный / исполнитель</th><th>Срок</th><th>Статус и прогресс</th><th>Действия</th></tr></thead>
          <tbody>
            <tr v-for="task in rows" :key="task.id">
              <td>
                <strong>{{ task.title }}</strong>
                <div v-for="item in task.items" :key="item.productId" class="mini">
                  {{ item.line }} · {{ item.name }} · {{ item.pack }} л · {{ item.completed }} из {{ item.quantity }} шт.
                </div>
              </td>
              <td>{{ employeeName(task.coordinator) }}<div class="mini">{{ task.assignee ? employeeName(task.assignee) : 'Ожидает назначения' }}</div></td>
              <td :class="{ 'danger-text': overdue(task) }">{{ showDate(task.deadline) }}<div v-if="overdue(task)" class="mini">Просрочена</div>
                <div v-else-if="task.completedAt && Date.parse(task.completedAt) > Date.parse(task.deadline)" class="mini">Выполнена с опозданием</div>
              </td>
              <td>{{ statuses[task.status] }} · {{ task.progress }}%<div v-if="task.note" class="mini">{{ task.note }}</div></td>
              <td><button type="button" class="btn slim" :disabled="busy" @click="openEdit(task)">{{ closed(task) ? 'Открыть' : 'Открыть задачу' }}</button></td>
            </tr>
            <tr v-if="!rows.length"><td colspan="5">Задач по этому фильтру нет.</td></tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style scoped>
.department-tasks { margin-block: 16px; }
.section-header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
.task-editor { margin-block: 14px; border: 1px solid var(--border, #cbd9d1); padding: 14px; border-radius: 12px; }
.task-editor fieldset { border:0; padding:0; min-width:0; }
.task-fields { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr)); align-items:end; gap:10px; margin-block:10px; }
.task-editor .actionbar, .totals { margin-block:12px; }
.table td { overflow-wrap:anywhere; }
</style>
