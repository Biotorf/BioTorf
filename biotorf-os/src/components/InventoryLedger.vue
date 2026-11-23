<script setup>
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue';
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
  receipt_powder: 'Приёмка порошка',
  receipt_paste: 'Приёмка пасты',
  production: 'Выпуск и расход сырья',
  reserve: 'Резерв под заказ',
  release: 'Снятие резерва',
  dispatch: 'Отгрузка со склада',
  return: 'Возврат на склад',
  adjustment: 'Корректировка по инвентаризации',
  reversal: 'Сторно',
};
const movementTypes = Object.keys(labels).filter((type) => !['reversal', 'receipt_paste'].includes(type));
const sourceTables = {
  logistics: 'Документ логистики',
  production: 'Производственная партия',
  orders: 'Заказ',
  shipments: 'Отгрузка CRM',
};
const sourceTypes = {
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
const error = ref('');
const formError = ref('');
const success = ref('');
const form = ref(null);
const ready = ref(false);
const unavailable = ref(false);
const canPost = computed(() => ready.value && !unavailable.value && !loading.value && !error.value);
let lastSubmission = null;
const warehouseListId = useId();
const orderListId = useId();
const sourceListId = useId();
const lotListId = useId();
const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 });
const signedNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3, signDisplay: 'exceptZero' });
const date = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' });

const labelSku = (sku) => sku === 'POWDER' ? 'Порошок-концентрат'
  : sku === 'PASTE' ? 'Паста (исторические партии)' : db.skuById(sku)?.name || sku;
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
const visibleBalances = computed(() => balances.value.filter((row) =>
  includesQuery([row.sku, labelSku(row.sku), row.lot, row.warehouse, ...Object.keys(row.reservations || {})])));
const visibleEvents = computed(() => events.value.filter((event) =>
  includesQuery([labels[event.type], event.reference, event.orderId, event.createdBy, event.source?.id,
    ...(event.lines || []).flatMap((line) => [labelSku(line.sku), line.sku, line.lot, line.warehouse])])));
const knownWarehouses = computed(() => [...new Set(balances.value.map((row) => row.warehouse))]);
const knownLots = computed(() => [...new Set(balances.value.map((row) => row.lot))]);
const finishedSkus = computed(() => [...new Set([
  ...(db.skus || []).map((row) => row.id),
  ...balances.value.map((row) => row.sku),
])].filter((sku) => !['POWDER', 'PASTE'].includes(sku)));
const sourceRows = computed(() => {
  const type = form.value?.type;
  const table = form.value?.collection;
  const rows = table === 'logistics' ? logisticsDocuments.value : db.data[table] || [];
  if (type === 'receipt_powder') return rows.filter((row) => row.kind === 'supply' && row.status === 'Принят'
    && row.items?.some((item) => item.material === 'powder' && item.qcStatus === 'Пройден'));
  if (type === 'production') return rows.filter((row) => row.status === 'Завершено' && ['Пройден', 'Отклонён'].includes(row.qcStatus));
  if (table === 'logistics') return rows.filter((row) => row.kind === 'dispatch');
  return rows;
});
const selectedSource = computed(() => sourceRows.value.find((row) => String(row.id) === form.value?.sourceId));
const reverseEvent = computed(() => events.value.find((event) => event.id === form.value?.reverseOf));
const sourceOptions = computed(() => sourceTypes[form.value?.type] || []);
const orderRequired = computed(() => ['reserve', 'release'].includes(form.value?.type));
const orderVisible = computed(() => orderRequired.value || ['dispatch', 'return'].includes(form.value?.type));

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
function line(sku = '', warehouse = '') {
  return { sku, lot: '', warehouse, qty: '' };
}
function changeType() {
  const draft = form.value;
  const warehouse = draft.lines[0]?.warehouse || '';
  draft.collection = sourceTypes[draft.type]?.[0] || '';
  draft.sourceId = '';
  draft.orderId = '';
  draft.lines = draft.type === 'production'
    ? [line('POWDER', warehouse), line('', warehouse)]
    : [line(draft.type === 'receipt_powder' ? 'POWDER' : '', warehouse)];
}
function showForm(type = canEdit('warehouse') && balances.value.length ? 'receipt_powder' : inventoryTypes.value[0], source = {}, orderId = '') {
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
  if (draft.type === 'receipt_powder') {
    draft.lines = record.items.filter((item) => item.material === 'powder' && item.qcStatus === 'Пройден')
      .map((item) => ({
        sku: 'POWDER', lot: item.lot, warehouse: record.warehouse || '',
        qty: String(Number(item.qty) * (item.unit === 'т' ? 1000 : 1)),
      }));
  } else if (draft.type === 'production') {
    const matchingWarehouses = [...new Set(balances.value.filter((row) =>
      row.sku === 'POWDER' && row.lot === record.inputLot && Number(row.available) > 0).map((row) => row.warehouse))];
    const warehouse = matchingWarehouses.length === 1 ? matchingWarehouses[0] : '';
    draft.lines = [{ sku: 'POWDER', lot: record.inputLot || '', warehouse, qty: String(record.powderUsedKg ?? '') }];
    if (record.qcStatus === 'Пройден') {
      draft.lines.push({ sku: record.sku || '', lot: record.lot || '', warehouse, qty: String(record.actualQty ?? '') });
    }
  } else if (['dispatch', 'return'].includes(draft.type)) {
    if (record.orderId) draft.orderId = record.orderId;
    if (draft.type !== 'dispatch') return;
    const items = Array.isArray(record.items) ? record.items : [];
    const suggested = items.filter((item) => item.sku || item.skuId).map((item) => {
      const sku = item.sku || item.skuId;
      const quantity = Number(item.packs ?? item.qty);
      const matches = balances.value.filter((row) => row.sku === sku
        && Number(row.available) + Number(row.reservations?.[draft.orderId] || 0) >= quantity);
      const match = quantity > 0 && matches.length === 1 ? matches[0] : null;
      return { sku, lot: match?.lot || '', warehouse: match?.warehouse || '', qty: quantity > 0 ? String(quantity) : '' };
    });
    if (suggested.length) draft.lines = suggested;
  }
}
watch(selectedSource, (record) => {
  if (form.value?.lines?.every((row) => !row.lot && !row.qty)) prefillSource(record);
});
function chooseSource() { prefillSource(selectedSource.value); }
function showLinkedForm() {
  const hash = location.hash;
  if (hash.split('?')[0] !== '#/warehouse') return;
  const query = new URLSearchParams(hash.split('?')[1]);
  const type = query.get('movement');
  if (!type || form.value) return;
  showForm(type, { collection: query.get('sourceCollection'), id: query.get('sourceId') || '' }, query.get('orderId') || '');
}
function showReverse(event) {
  if (!canPost.value || !canEdit('warehouse') || event.reversedBy || event.type === 'reversal') return;
  formError.value = '';
  success.value = '';
  lastSubmission = null;
  form.value = { type: 'reversal', reverseOf: event.id, reference: '' };
}
function closeForm() {
  if (saving.value) return;
  form.value = null;
  formError.value = '';
  lastSubmission = null;
  if (location.hash.startsWith('#/warehouse?')) history.replaceState(null, '', '#/warehouse');
}
function skuOptions(type) {
  if (type === 'receipt_powder') return ['POWDER'];
  if (type === 'production') return ['POWDER', ...finishedSkus.value];
  if (['opening', 'adjustment'].includes(type)) {
    const legacy = balances.value.some((row) => row.sku === 'PASTE') ? ['PASTE'] : [];
    return ['POWDER', ...legacy, ...finishedSkus.value];
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
  if (saving.value || !canPost.value) return;
  formError.value = '';
  saving.value = true;
  try {
    const payload = toPayload();
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
  logisticsApi.list().then((docs) => { logisticsDocuments.value = docs || []; }).catch(() => {});
  window.addEventListener('hashchange', showLinkedForm);
});
onBeforeUnmount(() => window.removeEventListener('hashchange', showLinkedForm));
</script>

<template>
  <section class="inventory">
    <div class="inventory-bar">
      <div v-if="ready" class="actionbar">
        <button class="btn slim" data-tour="warehouse-balance" :class="{ primary: tab === 'balances' }" :aria-pressed="tab === 'balances'" @click="tab = 'balances'">Остатки</button>
        <button class="btn slim" :class="{ primary: tab === 'history' }" :aria-pressed="tab === 'history'" @click="tab = 'history'">Журнал движений</button>
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
      <h2>{{ form.reverseOf ? 'Сторно складской операции' : 'Новая складская операция' }}</h2>
      <fieldset :disabled="saving">
        <p v-if="reverseEvent">{{ labels[reverseEvent.type] }} · {{ dateTime(reverseEvent.createdAt) }} · {{ reverseEvent.reference || reverseEvent.id }}</p>
        <div class="operation-fields">
          <label v-if="!form.reverseOf">Вид операции
            <select v-model="form.type" class="select" @change="changeType">
              <option v-for="type in inventoryTypes" :key="type" :value="type">{{ labels[type] }}</option>
            </select>
          </label>
          <label v-if="sourceOptions.length > 1">Вид документа
            <select v-model="form.collection" class="select" @change="form.sourceId = ''">
              <option v-for="table in sourceOptions" :key="table" :value="table">{{ sourceTables[table] }}</option>
            </select>
          </label>
          <label v-if="form.collection && form.collection !== 'orders'">
            {{ sourceTables[form.collection] }} · ID
            <input v-model="form.sourceId" class="input" :list="sourceListId" maxlength="100" @change="chooseSource" />
            <datalist :id="sourceListId"><option v-for="row in sourceRows" :key="row.id" :value="row.id">{{ crmTitle(row) }}</option></datalist>
          </label>
          <label v-if="orderVisible">Заказ · ID
            <input v-model="form.orderId" class="input" :list="orderListId" :required="orderRequired" maxlength="100" />
            <datalist :id="orderListId"><option v-for="order in db.orders" :key="order.id" :value="order.id">{{ crmTitle(order) }}</option></datalist>
          </label>
          <label>{{ form.reverseOf ? 'Причина сторно' : 'Основание' }}
            <input v-model="form.reference" class="input" maxlength="500" :required="!!form.reverseOf || ['opening', 'adjustment'].includes(form.type)" />
          </label>
        </div>

        <template v-if="!form.reverseOf">
          <button v-if="selectedSource && ['receipt_powder', 'production', 'dispatch'].includes(form.type)" type="button"
            class="btn slim ghost prefill" @click="chooseSource">Заполнить из документа</button>
          <p v-if="form.type === 'production'" class="mini">Укажите расход порошка и фактический выпуск по партиям. При отклонении контроля качества укажите расход сырья.</p>
          <p v-if="form.type === 'adjustment'" class="mini">Укажите разницу между фактическим и учётным остатком. Уменьшение записывается со знаком минус.</p>
          <div v-for="(row, index) in form.lines" :key="index" class="movement-line">
            <label>Товар
              <select v-model="row.sku" class="select" required>
                <option value="" disabled>Выберите товар</option>
                <option v-for="sku in skuOptions(form.type)" :key="sku" :value="sku">{{ labelSku(sku) }} · {{ sku }}</option>
              </select>
            </label>
            <label>Партия <input v-model="row.lot" class="input" :list="lotListId" required maxlength="100" /></label>
            <label>Склад <input v-model="row.warehouse" class="input" :list="warehouseListId" required maxlength="100" /></label>
            <label>Количество{{ row.sku ? ', ' + unitFor(row.sku) : '' }}
              <input v-model="row.qty" class="input" inputmode="decimal" required maxlength="24" />
            </label>
            <button type="button" class="btn slim ghost danger-text" :disabled="form.lines.length === 1"
              :aria-label="'Удалить строку ' + (index + 1)" @click="form.lines.splice(index, 1)">✕</button>
          </div>
          <datalist :id="warehouseListId"><option v-for="warehouse in knownWarehouses" :key="warehouse" :value="warehouse" /></datalist>
          <datalist :id="lotListId"><option v-for="lot in knownLots" :key="lot" :value="lot" /></datalist>
          <button type="button" class="btn slim ghost" @click="form.lines.push(line(form.type === 'receipt_powder' ? 'POWDER' : '', form.lines.at(-1)?.warehouse))">＋ Строка</button>
        </template>

        <p v-if="formError" class="danger-text" role="alert">{{ formError }}</p>
        <div class="actionbar operation-footer">
          <button type="submit" class="btn slim primary" :disabled="!canPost">{{ saving ? 'Проведение…' : form.reverseOf ? 'Провести сторно' : 'Провести операцию' }}</button>
          <button type="button" class="btn slim ghost" @click="closeForm">Отмена</button>
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
          <thead><tr><th>Товар</th><th>Партия</th><th>Склад</th><th>Ед.</th><th>В наличии</th><th>В резерве</th><th>Доступно</th></tr></thead>
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
            </tr>
            <tr v-if="!visibleBalances.length"><td colspan="7" class="empty">{{ query ? 'По этому запросу партий нет.' : 'Остатков в складском журнале пока нет.' }}</td></tr>
          </tbody>
        </table>
      </div>
      <div v-else class="table-wrap">
        <p v-if="events.length === 150" class="mini history-limit">Показаны последние 150 операций.</p>
        <table class="table">
          <thead><tr><th>Дата</th><th>Движение</th><th>Позиции</th><th>Основание</th><th>Сотрудник</th><th v-if="canEdit('warehouse')">Действие</th></tr></thead>
          <tbody>
            <tr v-for="event in visibleEvents" :key="event.id">
              <td>{{ dateTime(event.createdAt) }}</td>
              <td>{{ labels[event.type] || event.type }}<div v-if="event.reversedBy" class="mini">Сторнировано</div></td>
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
              <td v-if="canEdit('warehouse')"><button v-if="!event.reversedBy && event.type !== 'reversal'" class="btn slim ghost" :disabled="!!form || saving || !canPost" @click="showReverse(event)">Сторно</button></td>
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
