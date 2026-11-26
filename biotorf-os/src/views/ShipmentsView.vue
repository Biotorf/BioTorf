<script setup>
import { inventoryLink } from '@/utils/inventoryLink';
import { usePermissions } from '@/composables/usePermissions';
import StatusPill from '@/components/ui/StatusPill.vue';
import CrmDataTable from '@/components/CrmDataTable.vue';
// Раздел «Логистика»: реестры ПОСТАВОК (приход) и ВЫГРУЗОК (отгрузка) товара.
// Таблицы в стиле Excel: итоговые карточки, поиск, фильтр по статусу,
// редактирование позиций на странице, экспорт всего реестра в .xls/.csv,
// печать реестра и создание актов приёма-передачи под каждый документ.
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import LogisticsDocEditor from '@/components/forms/LogisticsDocEditor.vue';
import { toCsv, toXmlSpreadsheet, downloadBlob, printHtml, escapeHtml } from '@/utils/spreadsheet';

import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
const rowOpen = ref(false);
const editRec = ref(null);
const shipmentForm = ref(null);
const logisticsForm = ref(null);
const logisticsEditor = ref(null);

async function editShipment(record) {
  editRec.value = record;
  rowOpen.value = true;
  await nextTick();
  shipmentForm.value?.scrollIntoView({ block: 'start' });
}

const db = useDbStore();
const trainingActive = inject('trainingActive', ref(false));
const ui = useUiStore();
const { canEdit, canEditCollection } = usePermissions();
const { money, num } = useFormatters();

const routeQuery = () => new URLSearchParams(location.hash.split('?')[1]);
const targetShipment = ref(routeQuery().get('shipment'));
const tabFromHash = () => routeQuery().get('kind') === 'supply' ? 'supply' : 'dispatch';
const tab = ref(tabFromHash());
function locationTab(kind) { location.hash = '#/shipments?kind=' + kind; }
const readTab = () => { tab.value = tabFromHash(); targetShipment.value = routeQuery().get('shipment'); ui.filter = 'Все'; };
onMounted(() => window.addEventListener('hashchange', readTab));
onBeforeUnmount(() => window.removeEventListener('hashchange', readTab));
const syncing = ref(true);

onMounted(async () => {
  syncing.value = true;
  await db.syncLogistics({ uploadPending: !trainingActive.value }).catch(() => false);
  syncing.value = false;
});

const docs = computed(() => db.logistics.filter((d) => d.kind === tab.value));

const filtered = computed(() => {
  const q = ui.search.toLowerCase();
  return docs.value.filter((d) => {
    if (ui.filter !== 'Все' && d.status !== ui.filter) return false;
    if (!q) return true;
    return [d.number, d.party, d.warehouse, d.base, d.driver, d.vehicle, d.status,
      (d.items || []).map((i) => [i.name, i.lot].filter(Boolean).join(' ')).join(' '),
      d.act ? `акт ${d.act.number} ${d.act.type}` : 'без акта',
    ].join(' ').toLowerCase().includes(q);
  });
});

const sumOf = (d) => (d.items || []).reduce((s, it) => s + (Number(it.qty) || 0) * (Number(it.price) || 0), 0);
const qtyOf = (d) => (d.items || []).reduce((s, it) => s + (Number(it.qty) || 0), 0);

const stats = computed(() => ({
  count: docs.value.length,
  total: docs.value.reduce((s, d) => s + sumOf(d), 0),
  acts: docs.value.filter((d) => d.act).length,
  open: docs.value.filter((d) => !['Закрыт', 'Отменён', 'Оплачен'].includes(d.status)).length,
}));

const statusOptions = computed(() =>
  ['Все', ...Array.from(new Set(docs.value.map((d) => d.status)))]);

const itemsSummary = (d) => {
  const names = (d.items || []).map((it) => it.name).filter(Boolean);
  if (!names.length) return '—';
  return names.length <= 2 ? names.join(', ') : `${names[0]} +${names.length - 1} поз.`;
};

async function openEditor(doc = null, initialValues = undefined) {
  logisticsEditor.value = { doc, kind: doc?.kind || tab.value, initialValues };
  await nextTick();
  logisticsForm.value?.scrollIntoView({ block: 'start' });
}

function openShipmentDocument(shipment) {
  const existing = db.logistics.find((doc) => doc.shipmentId === shipment.id);
  if (existing) return openEditor(existing);
  const order = db.orderById(shipment.orderId);
  const farmId = shipment.farmId || order?.farmId;
  const items = shipment.items?.length ? shipment.items : order?.items?.length ? order.items : order?.sku ? [order] : [];
  return openEditor(null, {
    shipmentId: shipment.id, kind: 'dispatch', number: shipment.number, date: shipment.planDate || shipment.date,
    status: 'Создан', farmId, orderId: shipment.orderId, party: db.farmById(farmId)?.name,
    vehicle: shipment.vehicle, driver: shipment.driver,
    base: order ? `Заказ ${order.number || order.num || order.id}` : '',
    items: items.map((item) => {
      const skuId = item.skuId || item.sku;
      const sku = db.skuById(skuId);
      return { skuId, name: item.name || sku?.name || skuId, qty: item.packs ?? item.qty,
        unit: item.unit || 'шт.', price: item.price ?? sku?.price ?? 0, note: item.note || '' };
    }),
  });
}

watch(() => !syncing.value && canEdit('shipments') && targetShipment.value &&
  db.shipments.find((shipment) => shipment.id === targetShipment.value), (shipment) => {
  if (shipment) openShipmentDocument(shipment);
});

async function removeDoc(d) {
  if (!confirm(`Удалить документ ${d.number} (${d.party || '—'})?`)) return;
  try {
    await db.removeLogistics(d.id);
  } catch (error) {
    alert(error.message);
  }
}

// ── экспорт / печать всего реестра ──────────────────────────────────
function registryRows() {
  const head = tab.value === 'supply'
    ? ['Номер', 'Дата', 'Поставщик', 'Склад', 'Основание', 'Позиции', 'Кол-во', 'Сумма, сом', 'Статус', 'Акт']
    : ['Номер', 'Дата', 'Клиент/получатель', 'Склад', 'Транспорт', 'Водитель', 'Основание', 'Позиции', 'Кол-во', 'Сумма, сом', 'Статус', 'Акт'];
  const rows = filtered.value.map((d) => tab.value === 'supply'
    ? [d.number, d.date, d.party, d.warehouse, d.base, itemsSummary(d), qtyOf(d), Math.round(sumOf(d)), d.status, d.act ? `${d.act.type} №${d.act.number}` : 'нет']
    : [d.number, d.date, d.party, d.warehouse, d.vehicle, d.driver, d.base, itemsSummary(d), qtyOf(d), Math.round(sumOf(d)), d.status, d.act ? `${d.act.type} №${d.act.number}` : 'нет']);
  rows.push(['ИТОГО', '', '', '', '', '', '', Math.round(filtered.value.reduce((s, d) => s + sumOf(d), 0)), '', '']);
  return [head, ...rows];
}

function exportRegistry(fmt) {
  const rows = registryRows();
  const name = `${tab.value === 'supply' ? 'Postavki' : 'Vygruzki'}_${new Date().toISOString().slice(0, 10)}`;
  if (fmt === 'csv') downloadBlob(toCsv(rows), `${name}.csv`, 'text/csv;charset=utf-8');
  else downloadBlob(toXmlSpreadsheet(rows, name), `${name}.xls`, 'application/vnd.ms-excel');
}

function printRegistry() {
  const label = tab.value === 'supply' ? 'Реестр поставок' : 'Реестр выгрузок (отгрузок)';
  const rows = registryRows();
  const body = `<div class="org">ОсОО «Агро Трейд Плюс» · BIOTORF Business OS</div>
    <h1>${label}</h1><div class="small">на ${new Date().toLocaleDateString('ru-RU')} · документов: ${filtered.value.length}</div>
    <table><thead><tr>${rows[0].map((c) => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>
    <tbody>${rows.slice(1, -1).map((r) => `<tr>${r.map((c, j) => `<td class="${typeof c === 'number' ? 'num' : ''}">${typeof c === 'number' ? num(c) : escapeHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody>
    <tfoot><tr>${rows[rows.length - 1].map((c) => `<td class="${typeof c === 'number' ? 'num' : ''}">${typeof c === 'number' ? num(c) : escapeHtml(c)}</td>`).join('')}</tr></tfoot></table>`;
  printHtml(label, body);
}

function canPostReceipt(doc) {
  return canEdit('warehouse') && doc.kind === 'supply' && doc.status === 'Принят' &&
    doc.items?.some((item) => item.material === 'powder' && item.qcStatus === 'Пройден');
}

function canPostDispatch(doc) {
  return canEdit('warehouse') && doc.kind === 'dispatch' && !doc.shipmentId && doc.items?.some((item) => item.skuId) &&
    !['Черновик', 'Отменён', 'Отменен', 'Отменена', 'Отменено'].includes(doc.status);
}

</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1 data-tour="supply-view">Поставки и отгрузки</h1>
        <ManualLink />
        <div class="subtitle">Приёмка порошка и доставка готовой продукции.</div>
      <BackendBadge collection="shipments" />
      </div>
      <div v-if="canEdit('shipments')" class="actionbar">
        <button class="btn primary" data-tour="supply-create" @click="openEditor()">{{ tab === 'supply' ? 'Новая поставка' : 'Новая отгрузка' }}</button>
      </div>
    </div>

    <details class="panel logistics-extra export-tools">
      <summary>Экспорт документов</summary>
      <div class="actionbar">
        <button class="btn slim ghost" @click="exportRegistry('xls')" title="Скачать отфильтрованный реестр в Excel">⬇ Excel (.xls)</button>
        <button class="btn slim ghost" @click="exportRegistry('csv')" title="Скачать реестр в CSV">⬇ CSV</button>
        <button class="btn slim ghost" @click="printRegistry" title="Печать реестра / PDF">🖨 Печать</button>
      </div>
    </details>

    <div class="chips" style="margin-bottom:16px">
      <button class="btn slim" :class="{ primary: tab === 'dispatch' }" @click="locationTab('dispatch')">
        ➜ Выгрузки (отгрузки)
      </button>
      <button class="btn slim" :class="{ primary: tab === 'supply' }" @click="locationTab('supply')">
        ⬅ Поставки (приход)
      </button>
      <span v-if="syncing" class="mini right">синхронизация…</span>
    </div>

    <div v-if="logisticsEditor" ref="logisticsForm" class="logistics-form">
      <LogisticsDocEditor :key="logisticsEditor.doc?.id || logisticsEditor.kind"
        inline :doc="logisticsEditor.doc" :kind="logisticsEditor.kind" :initial-values="logisticsEditor.initialValues" @close="logisticsEditor = null" />
    </div>

    <div class="stats">
      <div class="stat"><div class="label">Документов</div><div class="val">{{ stats.count }}</div><div class="foot">{{ tab === 'supply' ? 'поставок' : 'выгрузок' }} в реестре</div></div>
      <div class="stat"><div class="label">Сумма реестра</div><div class="val">{{ money(stats.total) }}</div><div class="foot">по позициям документов</div></div>
      <div class="stat"><div class="label">Актов создано</div><div class="val">{{ stats.acts }}</div><div class="foot">под документы</div></div>
      <div class="stat"><div class="label">Не закрыто</div><div class="val">{{ stats.open }}</div><div class="foot">требуют внимания</div></div>
    </div>

    <div class="toolbar">
      <input v-model="ui.search" class="input" :placeholder="`Поиск по ${tab === 'supply' ? 'поставкам' : 'выгрузкам'}: номер, клиент, товар, акт…`">
      <select v-model="ui.filter" class="select" style="max-width:220px">
        <option v-for="s in statusOptions" :key="s">{{ s }}</option>
      </select>
    </div>

    <div v-if="filtered.length" class="logistics-grid">
      <article v-for="doc in filtered" :key="doc.id" class="panel logistics-card">
        <header>
          <h2>{{ doc.number }}</h2>
          <StatusPill :status="doc.status" />
        </header>
        <p class="subtitle">{{ [doc.party, doc.date, doc.warehouse].filter(Boolean).join(' · ') }}</p>
        <p>{{ itemsSummary(doc) }}</p>
        <div class="actionbar">
          <button class="btn slim" @click="openEditor(doc)">Открыть документ</button>
          <a v-if="canPostReceipt(doc)" :href="inventoryLink('receipt_powder', 'logistics', doc.id)">Провести приёмку</a>
          <a v-if="canPostDispatch(doc)" :href="inventoryLink('dispatch', 'logistics', doc.id, doc.orderId)">Со склада</a>
        </div>
      </article>
    </div>
    <p v-else class="empty">Документов нет.</p>
    <details class="panel logistics-extra">
      <summary>Таблица документов</summary>
      <CrmDataTable coll="logistics" :rows="filtered" empty="Документов нет.">
        <template #actions="{ row: doc }">
          <button class="btn slim ghost" @click="openEditor(doc)">Открыть</button>
          <a v-if="canPostReceipt(doc)" :href="inventoryLink('receipt_powder', 'logistics', doc.id)">Провести приёмку</a>
          <a v-if="canPostDispatch(doc)" :href="inventoryLink('dispatch', 'logistics', doc.id, doc.orderId)">Со склада</a>
          <button v-if="canEdit('shipments')" class="btn slim ghost danger-text" @click="removeDoc(doc)">Удалить</button>
        </template>
      </CrmDataTable>
    </details>
    <details v-if="tab === 'dispatch'" class="panel logistics-extra">
      <summary>Заказы к отгрузке</summary>
      <button v-if="canEditCollection('shipments')" class="btn slim" @click="editShipment(null)">Добавить отгрузку заказа</button>
      <div v-if="rowOpen" ref="shipmentForm" class="logistics-form">
        <CrmRowModal :key="editRec?.id || 'new'" inline coll="shipments" :record="editRec" @close="rowOpen = false; editRec = null" />
      </div>
      <CrmDataTable coll="shipments" :rows="db.data.shipments || []" empty="Отгрузок CRM нет.">
        <template #actions="{ row: s }">
          <button v-if="canEditCollection('shipments')" class="btn slim ghost" @click="editShipment(s)">Изменить</button>
          <button v-if="canEdit('shipments') && s.orderId" class="btn slim ghost" :disabled="syncing"
            @click="openShipmentDocument(s)">Документ и акт</button>
          <a v-if="canEdit('warehouse') && s.orderId" :href="inventoryLink('dispatch', 'shipments', s.id, s.orderId)">Со склада</a>
          <button v-if="s.journeyId" class="btn slim ghost" @click="ui.openJourney(s.journeyId)">Процесс</button>
        </template>
      </CrmDataTable>
    </details>
  </div>
</template>

<style scoped>
.logistics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 250px), 1fr)); gap: 12px; }
.logistics-card header { display: flex; justify-content: space-between; align-items: start; gap: 8px; }
.logistics-card .actionbar { align-items: center; }
.logistics-extra { margin-top: 14px; }
.logistics-extra summary { cursor: pointer; font-weight: 650; }
.logistics-extra .table-wrap, .logistics-extra .actionbar { margin-top: 12px; }
.logistics-form { margin-block: 12px; scroll-margin-top: 70px; }
.export-tools { margin: 0 0 12px; padding: 10px 15px; }
</style>
