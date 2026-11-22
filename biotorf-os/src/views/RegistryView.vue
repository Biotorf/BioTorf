<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { COLL_RU, crmFieldLabel, crmDisplayValue, REF_FIELD, REF_KINDS, crmFields, crmReferences, crmTitle, crmValue } from '@/data/crmFields';
import CrmDataTable from '@/components/CrmDataTable.vue';
import CrmRowModal from '@/components/CrmRowModal.vue';

const db = useDbStore();
const ui = useUiStore();
const { canEditCollection, canSeeFarm } = usePermissions();
const collections = Object.keys(COLL_RU);
const params = () => new URLSearchParams(location.hash.split('?')[1]);
const route = ref(params());
const search = ref('');
const selected = computed(() => route.value.get('id'));
const coll = computed(() => collections.includes(route.value.get('table')) ? route.value.get('table') : 'farms');
const rowsByTable = computed(() => Object.fromEntries(collections.map((key) => [
  key, (db.data[key] || []).filter((row) => {
    const farmId = key === 'farms' ? row.id : row.farmId;
    const farm = farmId && db.farmById(farmId);
    return !farm || canSeeFarm(farm);
  }),
])));
const recordIndex = computed(() => Object.fromEntries(collections.map((table) => [
  table, new Map(rowsByTable.value[table].map((row) => [String(row.id), row])),
])));
const referenceFields = computed(() => fields.value.filter((key) => key in REF_FIELD || key === 'refId'));
const records = computed(() => rowsByTable.value[coll.value]);
const fields = computed(() => crmFields(coll.value, records.value));
const matches = computed(() => {
  const value = search.value.trim().toLowerCase();
  return records.value.filter((row) => !value || fields.value.some((key) =>
    crmDisplayValue(crmValue(coll.value, row, key)).toLowerCase().includes(value) ||
    (referenceFields.value.includes(key) && linksFor(row, key).some(({ target }) =>
      target && crmDisplayValue(crmTitle(target)).toLowerCase().includes(value))),
  ));
});
const page = ref(1);
const pageSize = 50;
const pageCount = computed(() => Math.max(1, Math.ceil(matches.value.length / pageSize)));
const visibleRows = computed(() => matches.value.slice((page.value - 1) * pageSize, page.value * pageSize));
const record = computed(() => recordIndex.value[coll.value].get(selected.value));
const canWrite = computed(() => canEditCollection(coll.value));
const editing = ref(null);
const status = ref('');
const shareUrl = ref('');

const createRelated = {
  farms: { leads: 'farmId', contacts: 'farmId', clientNotes: 'farmId', clientDocs: 'farmId' },
  deals: { quotes: 'dealId', pilots: 'dealId' },
  pilots: { applications: 'pilotId', media: 'pilotId' },
  orders: { invoices: 'orderId', shipments: 'orderId', production: 'orderId', logistics: 'orderId' },
  invoices: { payments: 'invoiceId' },
  skus: { warehouse: 'sku', production: 'sku' },
};
const reverseKind = computed(() => Object.keys(REF_KINDS).find((kind) => REF_KINDS[kind] === coll.value));
const related = computed(() => {
  if (!record.value) return [];
  const outgoing = crmReferences(coll.value, record.value);
  const result = [];
  for (const [table, rows] of Object.entries(rowsByTable.value)) {
    for (const row of rows) {
      if (table === coll.value && row.id === record.value.id) continue;
      if (outgoing.some((link) => link.coll === table && String(link.id) === String(row.id)) ||
          crmReferences(table, row).some((link) => link.coll === coll.value && String(link.id) === String(record.value.id))) {
        result.push({ table, row });
      }
    }
  }
  return result;
});

function href(table, id = '') {
  const query = new URLSearchParams({ table });
  if (id) query.set('id', id);
  return '#/registry?' + query;
}
function chooseTable(table) { location.hash = href(table); }
function onHashChange() {
  route.value = params();
  status.value = '';
  shareUrl.value = '';
}
onMounted(() => window.addEventListener('hashchange', onHashChange));
onBeforeUnmount(() => window.removeEventListener('hashchange', onHashChange));
watch(coll, () => { search.value = ''; page.value = 1; });
watch(search, () => { page.value = 1; });
watch(pageCount, (total) => { page.value = Math.min(page.value, total); });
watch(coll, (table) => {
  if (['logistics', 'production'].includes(table)) db.syncLogistics().catch(() => { status.value = 'Не удалось обновить документы логистики.'; });
}, { immediate: true });

function linksFor(row, key) {
  return crmReferences(coll.value, row)
    .filter((link) => link.field === key && link.field !== 'items')
    .map((link) => ({
      ...link,
      target: recordIndex.value[link.coll].get(String(link.id)),
    }));
}
function openEditor(table, row = null, initialValues = {}, kind = 'dispatch') {
  if (table === 'logistics') {
    ui.openModal('Документ логистики', () => import('@/components/forms/LogisticsDocEditor.vue'), { doc: row, initialValues, kind });
  } else {
    editing.value = { table, row, initialValues };
  }
}
function addRelated(table, field) {
  const row = record.value;
  const farmId = coll.value === 'farms' ? row.id : row.farmId;
  const initial = field === 'refId' ? { refKind: reverseKind.value, refId: row.id } : { [field]: row.id };
  if (farmId && fieldsFor(table).includes('farmId')) initial.farmId = farmId;
  if (row.journeyId && fieldsFor(table).includes('journeyId')) initial.journeyId = row.journeyId;
  if (['invoices', 'shipments', 'payments'].includes(table)) initial.amount = row.amount ?? '';
  if (table === 'shipments' && Array.isArray(row.items)) initial.items = row.items;
  if (table === 'logistics') {
    initial.party = db.farmById(farmId)?.name || '';
    initial.base = row.number || row.num || row.id;
    initial.items = (Array.isArray(row.items) ? row.items : []).map((item) => ({
      skuId: item.sku || item.skuId || '', name: item.name || '',
      qty: item.packs ?? item.qty ?? 1, price: item.price ?? 0, unit: item.unit || 'шт.',
    }));
    if (!initial.items.length && (row.sku || row.product)) {
      initial.items.push({ skuId: row.sku || '', name: row.product || '', qty: row.qty || 1, unit: row.unit || 'шт.', price: 0 });
    }
  }
  openEditor(table, null, initial);
}
function fieldsFor(table) { return crmFields(table, []); }
async function share() {
  const url = new URL(href(coll.value, record.value.id), location.href).href;
  try {
    await navigator.clipboard.writeText(url);
    status.value = 'Ссылка скопирована.';
  } catch {
    shareUrl.value = url;
  }
}
async function remove(row) {
  const tableToRemove = coll.value;
  const linked = Object.entries(rowsByTable.value).some(([table, rows]) => rows.some((item) =>
    crmReferences(table, item).some((link) => link.coll === tableToRemove && String(link.id) === String(row.id)),
  ));
  const warning = linked ? ' Есть связанные записи. Их ссылки на эту запись перестанут открываться.' : '';
  if (!confirm(`Удалить «${crmTitle(row)}»?${warning}`)) return;
  try {
    if (tableToRemove === 'logistics') await db.removeLogistics(row.id);
    else await db.deleteRow(tableToRemove, row.id);
    if (coll.value === tableToRemove && selected.value === String(row.id)) location.hash = href(tableToRemove);
  } catch (e) {
    status.value = e.message;
  }
}
</script>

<template>
  <section>
    <div class="pagehead">
      <h1>Реестр CRM</h1>
      <div v-if="canWrite" class="actionbar">
        <template v-if="coll === 'logistics'">
          <button class="btn primary slim" @click="openEditor(coll, null, {}, 'supply')">＋ Поставка</button>
          <button class="btn primary slim" @click="openEditor(coll)">＋ Выгрузка</button>
        </template>
        <button v-else class="btn primary slim" @click="openEditor(coll)">＋ Добавить запись</button>
      </div>
    </div>

    <div class="toolbar registry-tools">
      <label>Таблица
        <select class="select" :value="coll" @change="chooseTable($event.target.value)">
          <option v-for="table in collections" :key="table" :value="table">{{ COLL_RU[table] }}</option>
        </select>
      </label>
      <input v-model="search" class="input" placeholder="Поиск по полям записи" aria-label="Поиск по полям записи" />
      <span>{{ matches.length }} записей</span>
    </div>

    <p v-if="status" role="status">{{ status }}</p>
    <section v-if="record" class="panel record">
      <div class="record-head">
        <h2>{{ crmTitle(record) }}</h2>
        <div class="actionbar">
          <button v-if="coll === 'leads'" class="btn slim" @click="ui.openLeadCard(record.id)">Квалификация и процесс</button>
          <button v-else-if="coll === 'journeys' || record.journeyId" class="btn slim" @click="ui.openJourney(record.journeyId || record.id)">Сквозной процесс</button>
          <button v-if="canWrite" class="btn slim" @click="openEditor(coll, record)">Изменить</button>
          <button class="btn slim" @click="share">Скопировать ссылку</button>
          <a class="btn slim ghost" :href="href(coll)">Закрыть</a>
        </div>
      </div>
      <input v-if="shareUrl" class="input" :value="shareUrl" readonly aria-label="Ссылка на запись" @focus="$event.target.select()" />
      <dl class="details">
        <template v-for="key in fields" :key="key">
          <dt>{{ crmFieldLabel(coll, key) }}</dt>
          <dd>
            <template v-if="linksFor(record, key).length">
              <template v-for="link in linksFor(record, key)" :key="link.id">
                <a v-if="link.target" :href="href(link.coll, link.id)">{{ crmTitle(link.target) }}</a>
                <span v-else>{{ link.id }}</span>
              </template>
            </template>
            <span v-else>{{ crmDisplayValue(crmValue(coll, record, key)) }}</span>
          </dd>
        </template>
      </dl>
      <h3>Связанные записи</h3>
      <ul v-if="related.length" class="related">
        <li v-for="{ table, row } in related" :key="table + ':' + row.id">
          <a :href="href(table, row.id)">{{ COLL_RU[table] }} · {{ crmTitle(row) }}</a>
        </li>
      </ul>
      <p v-else>Связанных записей пока нет.</p>
      <div class="actionbar">
        <template v-for="(field, table) in createRelated[coll]" :key="table">
          <button v-if="canEditCollection(table)" class="btn slim" @click="addRelated(table, field)">＋ {{ COLL_RU[table] }}</button>
        </template>
        <button v-if="canEditCollection('tasks') && reverseKind && coll !== 'tasks'" class="btn slim" @click="addRelated('tasks', 'refId')">＋ Задача</button>
      </div>
    </section>
    <p v-else-if="selected" role="status">Запись ещё загружается, удалена или недоступна.</p>

    <CrmDataTable :coll="coll" :rows="visibleRows" :columns="fields">
      <template #actions="{ row }">
        <a :href="href(coll, row.id)">{{ crmTitle(row) }}</a>
        <div v-if="canWrite" class="actionbar row-actions">
          <button class="btn slim ghost" @click="openEditor(coll, row)">Изменить</button>
          <button class="btn slim ghost danger-text" @click="remove(row)">Удалить</button>
        </div>
      </template>
      <template v-for="key in referenceFields" :key="key" #[key]="{ row, value }">
        <template v-if="linksFor(row, key).length">
          <template v-for="link in linksFor(row, key)" :key="link.id">
            <a v-if="link.target" :href="href(link.coll, link.id)">{{ crmTitle(link.target) }}</a>
            <span v-else>{{ link.id }}</span>
          </template>
        </template>
        <span v-else>{{ value }}</span>
      </template>
    </CrmDataTable>
    <div v-if="pageCount > 1" class="actionbar pagination">
      <button class="btn slim" :disabled="page === 1" @click="page--">Назад</button>
      <span>{{ page }} / {{ pageCount }}</span>
      <button class="btn slim" :disabled="page === pageCount" @click="page++">Дальше</button>
    </div>
    <CrmRowModal v-if="editing" :coll="editing.table" :record="editing.row" :initial-values="editing.initialValues" @close="editing = null" />
  </section>
</template>

<style scoped>
.registry-tools, .record-head, .row-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.registry-tools { margin-bottom: 12px; }
.registry-tools .input { max-width: 280px; }
.row-actions { flex-wrap: nowrap; }
.record { padding: 16px; margin-bottom: 14px; }
.record-head { justify-content: space-between; }
.details { display: grid; grid-template-columns: minmax(100px, 1fr) minmax(0, 4fr); gap: 6px 12px; }
dd { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.related { padding-inline-start: 20px; }
.pagination { margin-top: 12px; }
</style>
