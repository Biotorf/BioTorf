<script setup>
// «Задачи» (руководство v0.9 §7): реестр поручений — исполнитель, срок, статус.
// Клик по строке открывает карточку задачи; из неё — переход к связанному объекту.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';

const db = useDbStore();
const ui = useUiStore();
const { day } = useFormatters();

const STATUSES = ['Все', 'Открыта', 'В работе', 'Выполнена', 'Отменена'];
const PRIORITIES = ['Низкий', 'Средний', 'Высокий', 'Критический'];

const statusFilter = ref('Все');
const onlyLate = ref(false);

const isLate = (d) => {
  if (!d) return false;
  const t = new Date(d + 'T23:59:59');
  return t < new Date();
};

const tasks = computed(() =>
  db.tasks
    .filter((t) => statusFilter.value === 'Все' || t.status === statusFilter.value)
    .filter((t) => !onlyLate.value || (t.status !== 'Выполнена' && isLate(t.due)))
    .filter((t) => {
      const q = ui.search.toLowerCase();
      if (!q) return true;
      return [t.title, t.owner, t.status, t.priority].join(' ').toLowerCase().includes(q);
    })
);

const lateCount = computed(() => db.lateTasks.length);

// форма создания
const showNew = ref(false);
const form = ref({ title: '', owner: 'Менеджер А', due: '', priority: 'Средний', refKind: '', refId: '' });
const REF_KINDS = ['journey', 'deal', 'lead', 'farm', 'pilot', 'order', 'invoice', 'shipment'];
function create() {
  if (!form.value.title.trim()) return;
  db.addTask({ ...form.value, refId: form.value.refId || null, status: 'Открыта' });
  form.value = { title: '', owner: 'Менеджер А', due: '', priority: 'Средний', refKind: '', refId: '' };
  showNew.value = false;
}
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Задачи</h1>
        <div class="subtitle">Поручения с исполнителем, сроком и статусом · просрочено: <b :style="lateCount ? 'color:#c62828' : ''">{{ lateCount }}</b></div>
      </div>
      <button class="btn primary slim" @click="showNew = !showNew">＋ Создать задачу</button>
    </div>

    <div v-if="showNew" class="insight" style="flex-wrap:wrap;gap:8px;margin-bottom:14px">
      <input v-model="form.title" class="input" style="min-width:280px" placeholder="Название (измеримый результат)…" @keyup.enter="create" />
      <input v-model="form.owner" class="input" style="max-width:150px" placeholder="Исполнитель" />
      <input v-model="form.due" type="date" class="input" style="max-width:160px" />
      <select v-model="form.priority" class="select" style="max-width:150px"><option v-for="p in PRIORITIES" :key="p">{{ p }}</option></select>
      <select v-model="form.refKind" class="select" style="max-width:170px">
        <option value="">Без привязки</option><option v-for="k in REF_KINDS" :key="k" :value="k">{{ k }}</option>
      </select>
      <button class="btn slim primary" @click="create">Сохранить</button>
      <button class="btn slim" @click="showNew = false">Отмена</button>
    </div>

    <div class="insight" style="margin-bottom:14px;flex-wrap:wrap;gap:8px">
      <input :value="ui.search" @input="ui.search = $event.target.value" class="input" style="max-width:280px" placeholder="Поиск по задаче, исполнителю…" />
      <select v-model="statusFilter" class="select" style="max-width:170px"><option v-for="s in STATUSES" :key="s">{{ s }}</option></select>
      <label class="mini" style="display:flex;align-items:center;gap:6px"><input type="checkbox" v-model="onlyLate" /> только просроченные</label>
    </div>

    <section class="panel">
      <table class="table">
        <thead><tr><th>Задача</th><th>Исполнитель</th><th>Срок</th><th>Приоритет</th><th>Статус</th><th></th></tr></thead>
        <tbody>
          <tr v-for="t in tasks" :key="t.id" class="row-click" @click="ui.openRecord('task', t.id)">
            <td><b>{{ t.title }}</b></td>
            <td>{{ t.owner }}</td>
            <td :style="t.status !== 'Выполнена' && isLate(t.due) ? 'color:#c62828;font-weight:600' : ''">{{ day(t.due) }}</td>
            <td>{{ t.priority }}</td>
            <td><StatusPill :status="t.status" /></td>
            <td>
              <button v-if="t.status !== 'Выполнена'" class="btn slim" @click.stop="db.updateTask(t.id, { status: 'Выполнена' })">✓ Выполнить</button>
            </td>
          </tr>
          <tr v-if="!tasks.length"><td colspan="6" class="empty">Задач нет — создайте первую или измените фильтр</td></tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
</style>
