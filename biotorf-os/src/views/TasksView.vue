<script setup>
import { REF_KINDS, statusOptions } from '@/data/crmFields';
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Задачи» (руководство v0.9 §7): реестр поручений — исполнитель, срок, статус.
// Клик по строке открывает карточку задачи; из неё — переход к связанному объекту.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { isLate, useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import CrmImportModal from '@/components/CrmImportModal.vue';
import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';

const rowModal = ref(null);

const importColl = ref('');   // непусто — открыта модалка импорта

const db = useDbStore();
const ui = useUiStore();
const { canEditCollection } = usePermissions();

const STATUS_OPTIONS = computed(() => ['Все', ...statusOptions('tasks', db.tasks)]);
const statusFilter = ref('Все');
const onlyLate = ref(false);
const closed = (task) => ['Выполнена', 'Отменена'].includes(task.status);

const tasks = computed(() =>
  db.tasks
    .filter((t) => statusFilter.value === 'Все' || t.status === statusFilter.value)
    .filter((t) => !onlyLate.value || (!closed(t) && isLate(t.due)))
    .filter((t) => {
      const q = ui.search.toLowerCase();
      if (!q) return true;
      return [t.title, t.owner, t.status, t.priority].join(' ').toLowerCase().includes(q);
    })
);

const lateCount = computed(() => db.lateTasks.length);

function newTask(kind = null, id = null, followUp = false) {
  if (!canEditCollection('tasks')) return;
  const collection = Object.hasOwn(REF_KINDS, kind) ? REF_KINDS[kind] : null;
  const linked = collection && id ? db.data[collection]?.find((row) => row.id === id) : null;
  const initialValues = { owner: linked?.owner || ui.name, priority: 'Средний', status: 'Открыта' };
  if (collection && id) Object.assign(initialValues, { refKind: kind, refId: id });
  if (kind === 'lead' && !followUp) initialValues.due = linked?.next || '';
  rowModal.value = { coll: 'tasks', initialValues, followUp };
}

function readTaskRoute() {
  const [view, query] = location.hash.replace(/^#\/?/, '').split('?');
  if (view !== 'tasks') return;
  const params = new URLSearchParams(query);
  if (params.get('new') !== '1') {
    rowModal.value = null;
    return;
  }
  const lead = params.get('lead');
  if (lead) newTask('lead', lead);
  else newTask(params.get('kind'), params.get('id'), params.get('followUp') === '1');
}

function recordNextDate(task) {
  const editor = rowModal.value;
  if (!editor?.followUp || !task.due || task.refKind !== editor.initialValues.refKind || task.refId !== editor.initialValues.refId) return;
  const collection = REF_KINDS[task.refKind];
  const linked = db.data[collection]?.find((row) => row.id === task.refId);
  if (linked && 'next' in linked && canEditCollection(collection)) {
    db.editEntity(task.refKind, task.refId, { next: task.due });
  }
}

function closeEditor() {
  rowModal.value = null;
  if (location.hash.startsWith('#/tasks?')) history.replaceState(history.state, '', '#/tasks');
}

onMounted(() => {
  readTaskRoute();
  window.addEventListener('hashchange', readTaskRoute);
});
onBeforeUnmount(() => window.removeEventListener('hashchange', readTaskRoute));
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Задачи</h1>
        <ManualLink />
        <div class="subtitle">Поручения с исполнителем, сроком и статусом · просрочено: <b :style="lateCount ? 'color:#c62828' : ''">{{ lateCount }}</b></div>
      <BackendBadge collection="tasks" />
      </div>
        <div class="actionbar" style="margin-top:10px">
          <button class="btn slim" @click="importColl = 'tasks'" title="Загрузить задачи из CSV/JSON">⇪ Импорт</button>
          <button v-if="canEditCollection('tasks')" class="btn primary slim" @click="newTask()">＋ Создать задачу</button>
        </div></div>

    <CrmRowModal
      v-if="rowModal"
      inline
      :key="rowModal.record?.id || `new:${rowModal.initialValues?.refKind || ''}:${rowModal.initialValues?.refId || ''}`"
      :coll="rowModal.coll"
      :record="rowModal.record"
      :initial-values="rowModal.initialValues"
      @saved="recordNextDate"
      @close="closeEditor"
    />

    <div class="insight" style="margin-bottom:14px;flex-wrap:wrap;gap:8px">
      <input :value="ui.search" @input="ui.search = $event.target.value" class="input" style="max-width:280px" placeholder="Поиск по задаче, исполнителю…" />
      <select v-model="statusFilter" class="select" style="max-width:170px"><option v-for="s in STATUS_OPTIONS" :key="s">{{ s }}</option></select>
      <label class="mini" style="display:flex;align-items:center;gap:6px"><input type="checkbox" v-model="onlyLate" /> только просроченные</label>
    </div>

    <section class="panel">
      <CrmDataTable coll="tasks" :rows="tasks" empty="Задач нет.">
        <template #actions="{ row: t }">
          <button class="btn slim ghost" @click="ui.openRecord('task', t.id)">Открыть</button>
          <button v-if="!closed(t)" class="btn slim ghost" @click="db.updateTask(t.id, { status: 'Выполнена' })">Выполнить</button>
          <button class="btn slim ghost" @click="rowModal = { coll: 'tasks', record: t }">Изменить</button>
        </template>
      </CrmDataTable>
    </section>

    <CrmImportModal v-if="importColl" :coll="importColl" @close="importColl = ''" />
  </div>
</template>

<style scoped>
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
</style>
