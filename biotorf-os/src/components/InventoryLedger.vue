<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, useId, watch } from 'vue';
import CrmSelectField from '@/components/CrmSelectField.vue';
import { logisticsApi } from '@/api/logisticsClient';
import { inventoryApi } from '@/api/inventoryClient';
import { usePermissions } from '@/composables/usePermissions';
import { crmTitle } from '@/data/crmFields';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';

const db = useDbStore();
const ui = useUiStore();
const { canEdit } = usePermissions();
const emit = defineEmits(['legacy-mode']);
const labels = {
  opening: 'Начальный остаток',
  receipt_paste: 'Приёмка пасты',
  receipt_powder: 'Приёмка порошка (прежние поставки)',
  production: 'Выпуск и расход сырья',
  reserve: 'Резерв под заказ',
  release: 'Снятие резерва',
  dispatch: 'Отгрузка со склада',
  return: 'Возврат на склад',
  adjustment: 'Корректировка по инвентаризации',
  reversal: 'Сторно',
};
const movementTypes = Object.keys(labels).filter((type) => type !== 'reversal');
const sourceTables = {
  logistics: 'Документ логистики',
  production: 'Производственная партия',
  orders: 'Заказ',
  shipments: 'Отгрузка CRM',
};
const sourceTypes = {
  receipt_paste: ['logistics'],
  receipt_powder: ['logistics'],
  production: ['production'],
  reserve: ['orders'],
  release: ['orders'],
  dispatch: ['shipments', 'logistics'],
  return: ['shipments', 'logistics'],
};
const inventoryTypes = computed(() => canEdit('warehouse') ? movementTypes : ui.role === 'production' ? ['production'] : []);
const balances = ref([]);
const logisticsDocuments = ref([]);
const events = ref([]);
const query = ref('');
const tab = ref('balances');
const loading = ref(false);
const saving = ref(false);
const busyWarehouses = reactive(new Set());
const error = ref('');
const formError = ref('');
const success = ref('');
const form = ref(null);
const removeReason = ref(null);
const eventLabel = (event) => event.clearBalance ? 'Списание остатка партии' : (labels[event.type] || event.type);
const ready = ref(false);
const unavailable = ref(false);
const canPost = computed(() => ready.value && !unavailable.value && !loading.value && !error.value);
let lastSubmission = null;
let nextLineKey = 0;
const lotListId = useId();
const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 });
const signedNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3, signDisplay: 'exceptZero' });
const date = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' });

const labelSku = (sku) => sku === 'POWDER' ? 'Порошок-концентрат'
  : sku === 'PASTE' ? 'Паста-концентрат' : db.skuById(sku)?.name || sku;
const unitFor = (sku) => ['POWDER', 'PASTE'].includes(sku) ? 'кг' : 'шт.';
function qty(value) {
  return value == null || value === '' ? '—' : number.format(Number(value));
}
function dateTime(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? '—' : date.format(parsed);
}
function includesQuery(values) {
  const term = query.value.trim().toLowerCase();
  return !term || values.some((value) => String(value ?? '').toLowerCase().includes(term));
}
const visibleBalances = computed(() => balances.value.filter((row) => Number(row.onHand) > 0 &&
  includesQuery([row.sku, labelSku(row.sku), row.lot, row.warehouse, ...Object.keys(row.reservations || {})])));
const selectedBalance = ref(null);
function openBalanceHistory(row) {
  selectedBalance.value = row;
  query.value = '';
  tab.value = 'history';
}
const visibleEvents = computed(() => events.value.filter((event) =>
  (!selectedBalance.value || event.lines?.some((line) =>
    ['sku', 'lot', 'warehouse', 'unit'].every((key) => line[key] === selectedBalance.value[key]))) &&
  includesQuery([eventLabel(event), event.reference, event.orderId, event.createdBy, event.source?.id,
    ...(event.lines || []).flatMap((line) => [labelSku(line.sku), line.sku, line.lot, line.warehouse])])));
const knownWarehouses = computed(() => [...new Set([
  ...balances.value.map((row) => row.warehouse),
  ...logisticsDocuments.value.map((row) => row.warehouse),
  ...db.warehouse.map((row) => row.warehouse || row.location),
].filter(Boolean))]);
const knownLots = computed(() => [...new Set(balances.value.map((row) => row.lot))]);
const finishedSkus = computed(() => [...new Set([
  ...(db.skus || []).map((row) => row.id),
  ...balances.value.map((row) => row.sku),
])].filter((sku) => !['POWDER', 'PASTE'].includes(sku)));
const receiptSku = (type) => ({ receipt_paste: 'PASTE', receipt_powder: 'POWDER' })[type];
const sourceRows = computed(() => {
  const type = form.value?.type;
  const table = form.value?.collection;
  const rows = table === 'logistics' ? logisticsDocuments.value : db.data[table] || [];
  if (receiptSku(type)) return rows.filter((row) => row.kind === 'supply' && row.status === 'Принят'
    && row.items?.some((item) => item.material?.toUpperCase() === receiptSku(type) && item.qcStatus === 'Пройден'));
  if (type === 'production') return rows.filter((row) => row.status === 'Завершено' && ['Пройден', 'Отклонён'].includes(row.qcStatus));
  if (table === 'logistics') return rows.filter((row) => row.kind === 'dispatch' && !row.shipmentId);
  return rows;
});
const selectedSource = computed(() => sourceRows.value.find((row) => String(row.id) === (form.value?.collection === 'orders' ? form.value.orderId : form.value?.sourceId)));
const sourceChoices = computed(() => sourceRows.value.map((row) => ({ value: String(row.id), label: crmTitle(row) })));
const orderChoices = computed(() => db.orders.map((order) => ({
  value: String(order.id),
  label: [crmTitle(order), db.farmById(order.farmId)?.name].filter(Boolean).join(' · '),
})));
const reverseEvent = computed(() => events.value.find((event) => event.id === form.value?.reverseOf));
const sourceOptions = computed(() => sourceTypes[form.value?.type] || []);
const orderRequired = computed(() => ['reserve', 'release'].includes(form.value?.type));
const orderVisible = computed(() => orderRequired.value || ['dispatch', 'return'].includes(form.value?.type));

function setWarehouseBusy(row, busy) {
  if (busy) busyWarehouses.add(row);
  else busyWarehouses.delete(row);
}

function accept(data) {
  balances.value = data.balances;
  events.value = data.events;
  if (!ready.value && selectedSource.value && form.value?.lines?.every((row) => !row.warehouse)) {
    prefillSource(selectedSource.value);
  }
  ready.value = true;
  if (unavailable.value) {
    unavailable.value = false;
    emit('legacy-mode', false);
  }
}
function useLegacyMode() {
  ready.value = false;
  unavailable.value = true;
  balances.value = [];
  events.value = [];
  tab.value = 'balances';
  emit('legacy-mode', true);
}
async function refresh() {
  if (loading.value || saving.value) return;
  loading.value = true;
  error.value = '';
  try {
    accept(await inventoryApi.list());
  } catch (cause) {
    if (cause.inventoryUnavailable) useLegacyMode();
    else error.value = `Не удалось обновить склад. ${cause.message}`;
  } finally {
    loading.value = false;
  }
  if (canPost.value) showLinkedForm();
}
function line(sku = '', warehouse = '', lot = '', qty = '') {
  return { key: ++nextLineKey, sku, lot, warehouse, qty };
}
function changeType() {
  const draft = form.value;
  const warehouse = draft.lines[0]?.warehouse || '';
  draft.collection = sourceTypes[draft.type]?.[0] || '';
  draft.sourceId = '';
  draft.orderId = '';
  draft.lines = draft.type === 'production'
    ? [line('PASTE', warehouse), line('', warehouse)]
    : [line(receiptSku(draft.type) || '', warehouse)];
}
function showForm(type = canEdit('warehouse') && balances.value.length ? 'receipt_paste' : inventoryTypes.value[0], source = {}, orderId = '') {
  if (!canPost.value || !inventoryTypes.value.includes(type)) return;
  formError.value = '';
  success.value = '';
  lastSubmission = null;
  form.value = { type, collection: '', sourceId: '', orderId: '', reverseOf: '', reference: '', lines: [] };
  changeType();
  if (sourceTypes[type]?.includes(source.collection)) {
    form.value.collection = source.collection;
    form.value.sourceId = source.id;
  }
  form.value.orderId = orderId || (form.value.collection === 'orders' ? form.value.sourceId : '');
}
function prefillSource(record) {
  const draft = form.value;
  if (!record || !draft) return;
  if (receiptSku(draft.type)) {
    const sku = receiptSku(draft.type);
    draft.lines = record.items.filter((item) => item.material?.toUpperCase() === sku && item.qcStatus === 'Пройден')
      .map((item) => line(sku, record.warehouse || '', item.lot, String(Number(item.qty) * (item.unit === 'т' ? 1000 : 1))));
  } else if (draft.type === 'production') {
    const rawSku = Number(record.pasteUsedKg) > 0 ? 'PASTE' : 'POWDER';
    const matchingWarehouses = [...new Set(balances.value.filter((row) =>
      row.sku === rawSku && row.lot === record.inputLot && Number(row.available) > 0).map((row) => row.warehouse))];
    const warehouse = matchingWarehouses.length === 1 ? matchingWarehouses[0] : '';
    draft.lines = [line(rawSku, warehouse, record.inputLot || '', String((rawSku === 'PASTE' ? record.pasteUsedKg : record.powderUsedKg) ?? ''))];
    if (record.qcStatus === 'Пройден') {
      draft.lines.push(line(record.sku || '', warehouse, record.lot || '', String(record.actualQty ?? '')));
    }
  } else if (draft.type === 'release') {
    const reserved = balances.value.filter((row) => Number(row.reservations?.[draft.orderId]) > 0);
    draft.lines = reserved.length ? reserved.map((row) => line(row.sku, row.warehouse, row.lot,
      String(row.reservations[draft.orderId]))) : [line()];
  } else if (['dispatch', 'reserve'].includes(draft.type)) {
    if (record.orderId) draft.orderId = record.orderId;
    const items = record.items?.length ? record.items : [record];
    const suggested = items.filter((item) => item.sku || item.skuId).map((item) => {
      const sku = item.sku || item.skuId;
      const packageUnit = !item.unit || ['шт.', 'шт', 'штук', 'упак'].includes(item.unit);
      const quantity = Number(item.packs ?? (packageUnit ? item.qty : 0));
      const matches = balances.value.filter((row) => row.sku === sku && (!record.warehouse || row.warehouse === record.warehouse)
        && Number(row.available) + (draft.type === 'dispatch' ? Number(row.reservations?.[draft.orderId] || 0) : 0) >= quantity);
      const reservedMatches = draft.type === 'dispatch' ? matches.filter((row) =>
        Number(row.reservations?.[draft.orderId]) >= quantity) : [];
      const candidates = reservedMatches.length ? reservedMatches : matches;
      const match = quantity > 0 && candidates.length === 1 ? candidates[0] : null;
      return line(sku, match?.warehouse || record.warehouse || '', match?.lot || '', quantity > 0 ? String(quantity) : '');
    });
    if (suggested.length) draft.lines = suggested;
  }
}
watch(selectedSource, (record) => {
  if (!busyWarehouses.size && form.value?.lines?.every((row) => !row.lot && !row.qty)) prefillSource(record);
});
function chooseSource() { prefillSource(selectedSource.value); }
function chooseOrder() {
  if (!orderRequired.value) return;
  if (selectedSource.value) chooseSource();
  else form.value.lines = [line()];
}
function showLinkedForm() {
  const hash = location.hash;
  if (hash.split('?')[0] !== '#/warehouse') return;
  const query = new URLSearchParams(hash.split('?')[1]);
  const type = query.get('movement');
  if (!type || form.value) return;
  showForm(type, { collection: query.get('sourceCollection'), id: query.get('sourceId') || '' }, query.get('orderId') || '');
}
async function showRemoveBalance(row) {
  if (!canPost.value || !canEdit('warehouse') || form.value || Number(row.reserved)) return;
  showForm('adjustment');
  form.value.removeBalance = row;
  form.value.lines = [line(row.sku, row.warehouse, row.lot, '-' + row.onHand)];
  await nextTick();
  removeReason.value?.focus();
}
function showReverse(event) {
  if (!canPost.value || !canEdit('warehouse') || busyWarehouses.size || event.reversedBy || event.type === 'reversal') return;
  formError.value = '';
  success.value = '';
  lastSubmission = null;
  form.value = { type: 'reversal', reverseOf: event.id, reference: '' };
}
function closeForm() {
  if (saving.value || busyWarehouses.size) return;
  form.value = null;
  formError.value = '';
  lastSubmission = null;
  if (location.hash.startsWith('#/warehouse?')) history.replaceState(null, '', '#/warehouse');
}
function skuOptions(type) {
  if (receiptSku(type)) return [receiptSku(type)];
  if (type === 'production') return ['PASTE', 'POWDER', ...finishedSkus.value];
  if (['opening', 'adjustment'].includes(type)) {
    return ['PASTE', 'POWDER', ...finishedSkus.value];
  }
  return finishedSkus.value;
}
function toPayload() {
  const draft = form.value;
  const reference = draft.reference.trim();
  if (draft.type === 'reversal') {
    if (!reference) throw new Error('Укажите причину сторно.');
    return { type: draft.type, reverseOf: draft.reverseOf, reference };
  }
  const orderId = draft.orderId.trim();
  const sourceId = draft.collection === 'orders' ? orderId : draft.sourceId.trim();
  if (orderRequired.value && !orderId) throw new Error('Выберите заказ, к которому относится резерв.');
  if (!orderRequired.value && !sourceId && !reference) {
    throw new Error('Свяжите операцию с документом или укажите основание.');
  }
  const lines = draft.lines.map((row, index) => {
    const amount = row.qty.trim().replace(',', '.');
    const unit = unitFor(row.sku);
    const quantity = Number(amount);
    if (!row.sku || !row.lot.trim() || !row.warehouse.trim() || !/^-?\d+(\.\d{1,3})?$/.test(amount)
      || Math.abs(quantity) > 1e12 || !quantity || (unit === 'шт.' && !Number.isInteger(quantity))
      || (draft.type !== 'adjustment' && quantity < 0)) {
      throw new Error(`Строка ${index + 1}. Укажите товар, партию, склад и количество (целое для шт., до трёх знаков после запятой для кг).`);
    }
    return { sku: row.sku, lot: row.lot.trim(), warehouse: row.warehouse.trim(), unit, qty: amount };
  });
  return {
    type: draft.type, reference,
    ...(draft.removeBalance ? { clearBalance: true } : {}),
    ...(sourceId ? { source: { collection: draft.collection, id: sourceId } } : {}),
    ...(orderId ? { orderId } : {}),
    lines,
  };
}
function makeId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
}
async function submit() {
  if (saving.value || !canPost.value || busyWarehouses.size) return;
  formError.value = '';
  saving.value = true;
  try {
    const payload = toPayload();
    if (payload.source && payload.source.collection !== 'logistics') await db.pushCrmState();
    const hash = JSON.stringify(payload);
    if (hash !== lastSubmission?.hash) lastSubmission = { hash, id: makeId() };
    accept(await inventoryApi.post({ id: lastSubmission.id, ...payload }));
    success.value = 'Операция проведена.';
    tab.value = 'history';
    saving.value = false;
    closeForm();
  } catch (cause) {
    if (cause.inventoryUnavailable) useLegacyMode();
    else formError.value = cause.message;
  } finally {
    saving.value = false;
  }
}
function recordLink(table, id) {
  return '#/registry?' + new URLSearchParams({ table, id });
}
function effectsText(row) {
  const changes = [];
  if (Number(row.stockChange)) changes.push(`Наличие ${signedNumber.format(Number(row.stockChange))} ${row.unit}`);
  if (Number(row.reservedChange)) changes.push(`Резерв ${signedNumber.format(Number(row.reservedChange))} ${row.unit}`);
  return changes.length ? changes.join(' · ') : `${qty(row.qty)} ${row.unit}`;
}

onMounted(() => {
  refresh();
  db.refreshListOptions().catch(() => {});
  logisticsApi.list().then((docs) => { logisticsDocuments.value = docs || []; }).catch(() => {});
  window.addEventListener('hashchange', showLinkedForm);
});
onBeforeUnmount(() => window.removeEventListener('hashchange', showLinkedForm));
</script>

<template>
  <section class="inventory">
    <div class="inventory-bar">
      <div v-if="ready" class="actionbar">
        <button class="btn slim" data-tour="warehouse-balance" :class="{ primary: tab === 'balances' }" :aria-pressed="tab === 'balances'" @click="selectedBalance = null; tab = 'balances'">Остатки</button>
        <button class="btn slim" :class="{ primary: tab === 'history' }" :aria-pressed="tab === 'history'" @click="selectedBalance = null; tab = 'history'">Журнал движений</button>
      </div>
      <div class="actionbar">
        <button class="btn slim ghost" :disabled="loading || saving" @click="refresh">{{ loading ? 'Обновление…' : 'Обновить' }}</button>
        <button v-if="ready && inventoryTypes.length" class="btn primary slim" data-tour="warehouse-post" :disabled="!canPost || saving || !!form" @click="showForm()">＋ Складская операция</button>
      </div>
    </div>

    <p v-if="error" class="note danger-text" role="alert">{{ error }}</p>
    <p v-if="success" class="note" role="status">{{ success }}</p>
    <section v-if="unavailable" class="legacy-mode" data-tour="warehouse-balance">
      <p class="note" role="status">На сервере пока недоступен складской журнал. Ниже можно посмотреть прежний реестр. После обновления сервера нажмите «Обновить».</p>
      <slot name="legacy" />
    </section>
    <form v-if="ready && form" class="panel operation" @submit.prevent="submit">
      <h2>{{ form.removeBalance ? 'Удаление остатка партии' : form.reverseOf ? 'Сторно складской операции' : 'Новая складская операция' }}</h2>
      <fieldset :disabled="saving">
        <p v-if="reverseEvent">{{ labels[reverseEvent.type] }} · {{ dateTime(reverseEvent.createdAt) }} · {{ reverseEvent.reference || reverseEvent.id }}</p>
        <p v-if="form.removeBalance">
          Будет списано {{ qty(form.removeBalance.onHand) }} {{ form.removeBalance.unit }}.
          {{ labelSku(form.removeBalance.sku) }} · {{ form.removeBalance.lot }} · {{ form.removeBalance.warehouse }}
        </p>
        <div class="operation-fields">
          <label v-if="!form.reverseOf && !form.removeBalance">Вид операции
            <select v-model="form.type" class="select" :disabled="busyWarehouses.size > 0" @change="changeType">
              <option v-for="type in inventoryTypes" :key="type" :value="type">{{ labels[type] }}</option>
            </select>
          </label>
          <label v-if="sourceOptions.length > 1">Вид документа
            <select v-model="form.collection" class="select" :disabled="busyWarehouses.size > 0" @change="form.sourceId = ''">
              <option v-for="table in sourceOptions" :key="table" :value="table">{{ sourceTables[table] }}</option>
            </select>
          </label>
          <CrmSelectField v-if="form.collection && form.collection !== 'orders'" v-model="form.sourceId" class="field"
            :label="sourceTables[form.collection]" :options="sourceChoices" :disabled="busyWarehouses.size > 0"
            searchable placeholder="Выберите документ" @change="chooseSource" />
          <CrmSelectField v-if="orderVisible" v-model="form.orderId" class="field" label="Заказ" :options="orderChoices"
            :required="orderRequired" searchable placeholder="Выберите заказ" @change="chooseOrder" />
          <label>{{ form.removeBalance ? 'Причина списания' : form.reverseOf ? 'Причина сторно' : 'Основание' }}
            <input ref="removeReason" v-model="form.reference" class="input" maxlength="500" :required="!!form.reverseOf || ['opening', 'adjustment'].includes(form.type)" />
          </label>
        </div>

        <template v-if="!form.reverseOf && !form.removeBalance">
          <button v-if="selectedSource && ['receipt_paste', 'receipt_powder', 'production', 'dispatch', 'reserve', 'release'].includes(form.type)" type="button"
            class="btn slim ghost prefill" :disabled="busyWarehouses.size > 0" @click="chooseSource">Заполнить из документа</button>
          <p v-if="form.type === 'production'" class="mini">Укажите расход сырья и фактический выпуск по партиям. При отклонении контроля качества укажите расход сырья.</p>
          <p v-if="form.type === 'adjustment'" class="mini">Укажите разницу между фактическим и учётным остатком. Уменьшение записывается со знаком минус.</p>
          <div v-for="(row, index) in form.lines" :key="row.key" class="movement-line">
            <CrmSelectField v-model="row.sku" class="field" label="Товар"
              :options="skuOptions(form.type).map((sku) => ({ value: sku, label: `${labelSku(sku)} · ${sku}` }))"
              required searchable placeholder="Выберите товар" />
            <label>Партия <input v-model="row.lot" class="input" :list="lotListId" required maxlength="100" /></label>
            <CrmSelectField v-model="row.warehouse" class="field" label="Склад" :options="knownWarehouses" list-key="locations"
              required searchable placeholder="Выберите склад" @busy-change="setWarehouseBusy(row, $event)" />
            <label>Количество{{ row.sku ? ', ' + unitFor(row.sku) : '' }}
              <input v-model="row.qty" class="input" inputmode="decimal" required maxlength="24" />
            </label>
            <button type="button" class="btn slim ghost danger-text" :disabled="form.lines.length === 1 || busyWarehouses.size > 0"
              :aria-label="'Удалить строку ' + (index + 1)" @click="form.lines.splice(index, 1)">✕</button>
          </div>
          <datalist :id="lotListId"><option v-for="lot in knownLots" :key="lot" :value="lot" /></datalist>
          <button type="button" class="btn slim ghost" @click="form.lines.push(line(receiptSku(form.type) || '', form.lines.at(-1)?.warehouse))">＋ Строка</button>
        </template>

        <p v-if="formError" class="danger-text" role="alert">{{ formError }}</p>
        <div class="actionbar operation-footer">
          <button type="submit" class="btn slim primary" :disabled="!canPost || busyWarehouses.size > 0">{{ saving ? 'Проведение…' : form.removeBalance ? 'Списать остаток' : form.reverseOf ? 'Провести сторно' : 'Провести операцию' }}</button>
          <button type="button" class="btn slim ghost" :disabled="busyWarehouses.size > 0" @click="closeForm">Отмена</button>
        </div>
      </fieldset>
    </form>

    <p v-if="!ready && loading" role="status">Загрузка складского журнала…</p>
    <div v-if="ready">
      <div class="toolbar inventory-filter">
        <input v-model="query" class="input" aria-label="Поиск по складу" placeholder="Товар, партия, склад или заказ" type="search" />
      </div>
      <div v-if="tab === 'balances'" class="table-wrap">
        <table class="table">
          <thead><tr><th>Товар</th><th>Партия</th><th>Склад</th><th>Ед.</th><th>В наличии</th><th>В резерве</th><th>Доступно</th><th>Действия</th></tr></thead>
          <tbody>
            <tr v-for="row in visibleBalances" :key="JSON.stringify([row.sku, row.lot, row.warehouse, row.unit])">
              <td><b>{{ labelSku(row.sku) }}</b><div class="mini">{{ row.sku }}</div></td>
              <td>{{ row.lot }}</td><td>{{ row.warehouse }}</td><td>{{ row.unit }}</td>
              <td>{{ qty(row.onHand) }}</td>
              <td>{{ qty(row.reserved) }}
                <details v-if="Object.keys(row.reservations || {}).length">
                  <summary class="mini">Заказы</summary>
                  <div v-for="(amount, id) in row.reservations" :key="id"><a :href="recordLink('orders', id)">{{ db.orderById(id)?.number || id }}</a> · {{ qty(amount) }}</div>
                </details>
              </td>
              <td><b>{{ qty(row.available) }}</b></td>
              <td class="actionbar">
                <button type="button" class="btn slim" @click="openBalanceHistory(row)">Движения партии</button>
                <button v-if="canEdit('warehouse')" type="button" class="btn slim ghost danger-text"
                  :disabled="!canPost || !!form || Number(row.reserved) > 0"
                  @click="showRemoveBalance(row)">Удалить</button>
                <span v-if="canEdit('warehouse') && Number(row.reserved) > 0" class="mini">Сначала снимите резерв</span>
              </td>
            </tr>
            <tr v-if="!visibleBalances.length"><td colspan="8" class="empty">{{ query ? 'По этому запросу партий нет.' : 'Остатков в складском журнале пока нет.' }}</td></tr>
          </tbody>
        </table>
      </div>
      <div v-else class="table-wrap">
        <p v-if="selectedBalance" class="mini">Движения партии {{selectedBalance.lot}} · {{selectedBalance.warehouse}}
          <button type="button" class="btn slim ghost" @click="selectedBalance = null">Показать все</button>
        </p>
        <p v-if="canEdit('warehouse')" class="mini">Чтобы убрать ошибочное движение из расчёта остатков, нажмите «Отменить операцию (сторно)».</p>
        <p v-if="events.length === 150" class="mini history-limit">Показаны последние 150 операций.</p>
        <table class="table">
          <thead><tr><th>Дата</th><th>Движение</th><th>Позиции</th><th>Основание</th><th>Сотрудник</th><th v-if="canEdit('warehouse')">Действие</th></tr></thead>
          <tbody>
            <tr v-for="event in visibleEvents" :key="event.id">
              <td>{{ dateTime(event.createdAt) }}</td>
              <td>{{ eventLabel(event) }}<div v-if="event.reversedBy" class="mini">Сторнировано</div></td>
              <td class="ledger-lines">
                <div v-for="(row, index) in event.lines" :key="index">
                  {{ labelSku(row.sku) }} · {{ row.lot }} · {{ row.warehouse }} · {{ effectsText(row) }}
                </div>
                <small v-if="event.reverseOf">Сторно операции {{ event.reverseOf }}</small>
              </td>
              <td class="ledger-lines">
                <a v-if="event.source && sourceTables[event.source.collection]" :href="recordLink(event.source.collection, event.source.id)">{{ sourceTables[event.source.collection] }} · {{ event.sourceSnapshot?.number || event.source.id }}</a>
                <div v-if="event.orderId && event.source?.collection !== 'orders'"><a :href="recordLink('orders', event.orderId)">Заказ · {{ event.orderId }}</a></div>
                <div v-if="event.reference">{{ event.reference }}</div>
              </td>
              <td>{{ event.createdBy || '—' }}</td>
              <td v-if="canEdit('warehouse')"><button v-if="!event.reversedBy && event.type !== 'reversal'" class="btn slim ghost" :disabled="!!form || saving || !canPost" @click="showReverse(event)">Отменить операцию (сторно)</button></td>
            </tr>
            <tr v-if="!visibleEvents.length"><td :colspan="canEdit('warehouse') ? 6 : 5" class="empty">{{ query ? 'Движения не найдены.' : 'Проведённых движений пока нет.' }}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<style scoped>
.inventory-bar, .operation-footer { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.operation { margin-block: 12px; padding: 14px; }
.operation h2 { margin: 0 0 12px; }
.operation fieldset { display: grid; min-width: 0; padding: 0; margin: 0; border: 0; gap: 8px; }
.operation-fields, .movement-line { display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); align-items: end; gap: 8px; }
.movement-line { grid-template-columns: minmax(160px, 2fr) repeat(3, minmax(110px, 1fr)) auto; padding-block: 8px; border-bottom: 1px solid #e4ebe6; }
.operation label { display: grid; gap: 4px; font-size: 13px; }
.operation .input, .operation .select { width: 100%; min-width: 0; }
.operation-footer { justify-content: flex-start; margin-top: 6px; }
.inventory-filter { margin: 12px 0; }
.prefill { justify-self: start; }
.history-limit { margin: 6px 8px; }
.inventory-filter input { max-width: 340px; }
.ledger-lines { min-width: 180px; white-space: normal; overflow-wrap: anywhere; }
.ledger-lines > div + div { margin-top: 4px; }
@media (max-width: 755px) {
  .movement-line { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
}
</style>
