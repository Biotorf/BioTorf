<script setup>
import { FINISHED_WAREHOUSE, isFinished, PASTE, RAW_WAREHOUSE, stockUnit } from '@/data/stockCatalog';
// Редактор поставок и отгрузок.
// Таблица позиций редактируется прямо в ячейках — как в Excel:
//   товар | кол-во | ед. | цена | сумма (авто) | примечание.
// Кнопки: добавить/удалить строку, сохранить, создать акт (печать + сохранение в документе),
// скачать .xls / .csv всего реестра — в ShipmentsView.
import { computed, onMounted, reactive, ref, useId } from 'vue';
import CrmSelectField from '@/components/CrmSelectField.vue';
import { useDbStore } from '@/stores/db';
import { REQUISITE_FIELDS, COMPANY_CONTACT_FIELDS } from '@/data/requisites';
import { crmFieldLabel, LOGISTICS_KINDS } from '@/data/crmFields';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import { usePermissions } from '@/composables/usePermissions';
import { toCsv, toXmlSpreadsheet, downloadBlob, printHtml, escapeHtml } from '@/utils/spreadsheet';

const props = defineProps({
  doc: { type: Object, default: null },   // существующий документ или null (создание)
  kind: { type: String, default: 'supply' },
  initialValues: { type: Object, default: () => ({}) },
  inline: Boolean,
});
const emit = defineEmits(['close']);

const db = useDbStore();
const ui = useUiStore();
const { money, num } = useFormatters();
const { canEdit, canSeeFarm } = usePermissions();
onMounted(() => db.refreshListOptions().catch(() => {}));
const canWrite = computed(() => canEdit('shipments'));
const formId = useId();
const fieldId = (key) => `${formId}-${key}`;

const label = (key) => crmFieldLabel('logistics', key);
const savedDoc = ref(props.doc?.id && !String(props.doc.id).startsWith('NEW') ? props.doc : null);
const isNew = computed(() => !savedDoc.value);
const shipmentId = (props.doc || props.initialValues)?.shipmentId || '';
const clientId = shipmentId ? `LOC-${shipmentId}` : db.uid('LOC');
const saveError = ref('');
const saving = ref(false);
const busyLists = reactive(new Set());
const disabled = computed(() => saving.value || busyLists.size > 0 || !canWrite.value);
const today = new Date().toISOString().slice(0, 10);
let nextItemKey = 0;

const source = props.doc || props.initialValues;
const form = reactive({
  kind: source?.kind || props.kind,
  number: source?.number || genNumber(source?.kind || props.kind),
  date: source?.date || today,
  status: source?.status || 'Черновик',
  party: source?.party || '',
  farmId: source?.farmId || '',
  orderId: source?.orderId || '',
  warehouse: source?.warehouse || ((source?.kind || props.kind) === 'supply' ? RAW_WAREHOUSE : ''),
  vehicle: source?.vehicle || '',
  driver: source?.driver || '',
  base: source?.base || '',
  note: source?.note || '',
  items: source?.items?.length
    ? source.items.map((item) => itemDraft(item))
    : [emptyItem(source?.kind || props.kind)],
});

function itemDraft(item) {
  return { ...item, key: ++nextItemKey };
}

function emptyItem(kind) {
  return itemDraft({ skuId: '', name: '', qty: 1, unit: 'шт.', price: 0, note: '' });
}

function genNumber(kind) {
  return (kind === 'supply' ? 'П-' : 'В-') + clientId.slice(-8).toUpperCase();
}

const STATUSES = ['Черновик', 'Создан', 'На проверке', 'Принят', 'Отгружено', 'Доставлено', 'Оплачен', 'Закрыт', 'Отменён'];
const UNITS = ['л', 'кг', 'шт.', 'упак', 'т', 'м²'];

const isDispatch = computed(() => form.kind === 'dispatch');
const editorTitle = computed(() => isNew.value
  ? (isDispatch.value ? 'Новая отгрузка' : 'Новая поставка')
  : `Документ ${isDispatch.value ? 'отгрузки' : 'поставки'} ${form.number}`);
const customers = computed(() => db.farms.filter(canSeeFarm).map((farm) => ({ value: farm.id, label: farm.name || farm.id })));
const orders = computed(() => db.orders.filter((order) => {
  const farm = db.farmById(order.farmId);
  return (!farm || canSeeFarm(farm)) && (!form.farmId || !order.farmId || order.farmId === form.farmId);
}).map((order) => ({
  value: order.id,
  label: [order.number || order.num || order.id, db.farmById(order.farmId)?.name].filter(Boolean).join(' · '),
})));
const warehouses = computed(() => [...new Set([
  RAW_WAREHOUSE, FINISHED_WAREHOUSE,
  ...db.warehouse.map((row) => row.warehouse || row.location),
  ...db.logistics.map((row) => row.warehouse),
].filter(Boolean))]);
const suppliers = computed(() => logisticsOptions('party', 'supply'));
const vehicles = computed(() => logisticsOptions('vehicle'));
const drivers = computed(() => logisticsOptions('driver'));
const products = computed(() => (isDispatch.value ? db.skus.filter(isFinished) : [PASTE, ...db.skus]).map((sku) => ({
  value: sku.id,
  label: [sku.name || sku.id, sku.pack ? `${sku.pack} л` : '', sku.id].filter(Boolean).join(' · '),
})));
const selectedOrder = computed(() => db.orderById(form.orderId));
const hasItems = computed(() => form.items.some((item) => item.skuId || item.name || item.material));
const orderItems = computed(() => {
  const order = selectedOrder.value;
  if (!order) return [];
  const items = order.items?.length ? order.items : order.sku ? [order] : [];
  return items.filter((item) => item.sku || item.skuId).map((item) => {
    const skuId = item.sku || item.skuId;
    const sku = db.skuById(skuId);
    return {
      skuId, name: item.name || sku?.name || skuId, qty: item.packs ?? item.qty ?? 1,
      unit: item.unit || 'шт.', price: item.price ?? sku?.price ?? 0, note: item.note || '',
    };
  });
});
let previousFarmId = form.farmId;
let previousOrderId = form.orderId;

function logisticsOptions(key, kind = 'dispatch') {
  return [...new Set(db.logistics.filter((row) => row.kind === kind).map((row) => row[key]).filter(Boolean))];
}

function setListBusy(key, busy) {
  if (busy) busyLists.add(key);
  else busyLists.delete(key);
}

function applyFarm(id) {
  const previous = db.farmById(previousFarmId);
  const farm = db.farmById(id);
  if (!form.party || form.party === previous?.name) form.party = farm?.name || '';
  previousFarmId = id;
}

function chooseFarm(id) {
  applyFarm(id);
  if (id && selectedOrder.value?.farmId && selectedOrder.value.farmId !== id) {
    form.orderId = '';
    chooseOrder('');
  }
}

function useOrderItems() {
  if (orderItems.value.length) form.items = orderItems.value.map(itemDraft);
}

const orderBase = (order) => order ? `Заказ ${order.number || order.num || order.id}` : '';

function chooseOrder(id) {
  const order = db.orderById(id);
  if (!form.base || form.base === orderBase(db.orderById(previousOrderId))) form.base = orderBase(order);
  previousOrderId = id;
  if (!order) return;
  if (order.farmId) {
    form.farmId = order.farmId;
    applyFarm(order.farmId);
  }
  if (!hasItems.value) useOrderItems();
}

function closeEditor() {
  emit('close');
  if (!props.inline) ui.closeModal();
}

const lineSum = (it) => (Number(it.qty) || 0) * (Number(it.price) || 0);
const totalQty = computed(() => form.items.reduce((s, it) => s + (Number(it.qty) || 0), 0));
const totalPrice = computed(() => form.items.reduce((s, it) => s + lineSum(it), 0));

const addRow = () => form.items.push(emptyItem(form.kind));
const removeRow = (i) => {
  if (form.items.length > 1) form.items.splice(i, 1);
};

function onSku(item, id) {
  if (!id) return;
  const sku = id === PASTE.id ? PASTE : db.skuById(id);
  item.name = sku.name;
  if (!isDispatch.value) {
    item.material = id === PASTE.id ? 'paste' : '';
    item.unit = stockUnit(sku);
    if (!form.items.some((row) => row !== item && (row.skuId || row.material))) {
      form.warehouse = isFinished(sku) ? FINISHED_WAREHOUSE : RAW_WAREHOUSE;
    }
  }
  if (!item.price) item.price = Number(sku.price) || 0;
}

const docPayload = () => ({
  kind: form.kind,
  shipmentId: shipmentId || null,
  number: form.number.trim(),
  date: form.date,
  status: form.status,
  party: form.party.trim(),
  farmId: form.farmId || null,
  orderId: form.orderId || null,
  warehouse: form.warehouse.trim(),
  vehicle: form.vehicle.trim(),
  driver: form.driver.trim(),
  base: form.base.trim(),
  note: form.note.trim(),
  act: savedDoc.value?.act || null,
  items: form.items.map((it) => ({
    skuId: it.skuId, name: String(it.name || '').trim(),
    qty: Number(it.qty) || 0, unit: it.unit,
    price: Number(it.price) || 0, note: (it.note || '').trim(),
    material: it.material || '', lot: (it.lot || '').trim(), qcStatus: it.qcStatus || '',
  })),
});

function validatePayload(payload) {
  payload.items = payload.items.filter((item) => item.name || item.skuId || item.material);
  if (!payload.number) throw new Error('Укажите номер документа.');
  if (!payload.items.length) throw new Error('Добавьте хотя бы одну позицию.');
  const receiving = payload.kind === 'supply' && payload.status === 'Принят';
  if (receiving && !payload.warehouse) throw new Error('Выберите склад назначения поставки.');
  for (const item of payload.items) {
    if (!Number.isFinite(item.qty) || item.qty <= 0 || !Number.isFinite(item.price) || item.price < 0) {
      throw new Error('Укажите положительное количество и неотрицательную цену каждой позиции.');
    }
    if (!isRawMaterial(item)) {
      const raw = item.skuId && db.skuById(item.skuId)?.stockType === 'raw';
      if (receiving && raw && (!item.lot || item.unit !== 'кг')) {
        throw new Error('Для сырья укажите партию и массу в килограммах.');
      }
      if (receiving && !raw && (!item.skuId || !item.lot || !Number.isInteger(item.qty) ||
          !['шт.', 'шт', 'штук', 'упак', 'упак.'].includes(item.unit))) {
        throw new Error('Для приёмки товара выберите его из каталога, укажите партию и целое количество в штуках или упаковках.');
      }
      continue;
    }
    if (payload.kind !== 'supply' || !item.lot || !['кг', 'т'].includes(item.unit)) {
      throw new Error('Для сырья укажите партию поставщика и массу в кг или т.');
    }
    if (payload.status === 'Принят' && item.qcStatus !== 'Пройден') {
      throw new Error('Перед приёмкой подтвердите контроль качества каждой партии сырья.');
    }
  }
}

async function persist(payload) {
  validatePayload(payload);
  if (payload.shipmentId || payload.issueAct) await db.pushCrmState();
  const document = isNew.value
    ? await db.addLogistics({ ...payload, clientId })
    : await db.updateLogistics(savedDoc.value.id, payload);
  savedDoc.value = document;
  return document;
}

async function save(closeAfter = true) {
  if (disabled.value) return;
  saving.value = true;
  saveError.value = '';
  try {
    const document = await persist(docPayload());
    if (String(document.id).startsWith('LOC-')) {
      saveError.value = 'Документ пока сохранён только на этом устройстве. Откройте реестр после восстановления связи.';
    } else if (closeAfter) closeEditor();
  } catch (error) {
    saveError.value = error.message;
  } finally {
    saving.value = false;
  }
}

function isRawMaterial(item) { return ['powder', 'paste'].includes(item.material); }

function addPasteRow() {
  const material = { ...emptyItem(form.kind), skuId: PASTE.id, name: PASTE.name, material: 'paste', lot: '', unit: 'кг', qcStatus: 'Ожидается' };
  const first = form.items[0];
  if (!hasItems.value) form.warehouse = RAW_WAREHOUSE;
  if (form.items.length === 1 && !first.skuId && !first.name) form.items.splice(0, 1, material);
  else form.items.push(material);
}

// ── Акт приёма-передачи под документ ────────────────────────────────
function actRows() {
  const rows = [['№', 'Наименование', 'Кол-во', 'Ед.', 'Цена, сом', 'Сумма, сом']];
  form.items.forEach((it, i) => {
    if (!it.name && !it.skuId) return;
    const description = isRawMaterial(it) && it.lot ? `${it.name || 'Сырьё'} · партия ${it.lot}` : it.name || it.skuId;
    rows.push([i + 1, description, Number(it.qty) || 0, it.unit, Number(it.price) || 0, Math.round(lineSum(it))]);
  });
  rows.push(['', '', '', '', 'ИТОГО:', Math.round(totalPrice.value)]);
  return rows;
}

function partyDetails(profile) {
  return [...REQUISITE_FIELDS, ...COMPANY_CONTACT_FIELDS]
    .filter(([key]) => profile[key])
    .map(([key, label]) => `<div>${escapeHtml(label)}: ${escapeHtml(profile[key])}</div>`)
    .join('');
}

function buildActHtml(actMeta) {
  const label = isDispatch.value ? 'Грузополучатель' : 'Получатель (Покупатель)';
  const supplier = isDispatch.value ? 'Грузоотправитель' : 'Поставщик';
  const rows = actRows().map((r, idx) => idx === 0
    ? `<tr>${r.map((c, j) => `<th class="${j >= 2 ? 'num' : ''}">${escapeHtml(c)}</th>`).join('')}</tr>`
    : `<tr>${r.map((c, j) => `<td class="${j >= 2 ? 'num' : ''}">${typeof c === 'number' ? num(c) : escapeHtml(c)}</td>`).join('')}</tr>`
  ).join('');
  return `
  <div class="org">${escapeHtml(actMeta.organization.shortName || actMeta.organization.legalName)}</div>
  <h1>${escapeHtml(actMeta.type)} № ${escapeHtml(actMeta.number)} от ${new Date(actMeta.date + 'T12:00:00').toLocaleDateString('ru-RU')}</h1>
  <div class="small">к документу ${isDispatch.value ? 'выгрузки (отгрузки)' : 'поставки'} № ${escapeHtml(form.number)} от ${new Date(form.date + 'T12:00:00').toLocaleDateString('ru-RU')}</div>
  <div class="grid">
    <div style="flex:1 1 220px; min-width:0; overflow-wrap:anywhere"><b>${supplier}</b>${partyDetails(isDispatch.value ? actMeta.organization : actMeta.counterparty)}</div>
    <div style="flex:1 1 220px; min-width:0; overflow-wrap:anywhere"><b>${label}</b>${partyDetails(isDispatch.value ? actMeta.counterparty : actMeta.organization)}</div>
    ${form.warehouse ? `<div><b>Склад</b>${escapeHtml(form.warehouse)}</div>` : ''}
    ${form.vehicle ? `<div><b>Транспорт</b>${escapeHtml(form.vehicle)}</div>` : ''}
    ${form.driver ? `<div><b>Водитель/экспедитор</b>${escapeHtml(form.driver)}</div>` : ''}
    ${form.base ? `<div><b>Основание</b>${escapeHtml(form.base)}</div>` : ''}
  </div>
  <p>Мы, нижеподписавшиеся, составили настоящий акт о том, что по указанному документу произведена
  ${isDispatch.value ? 'выгрузка (отгрузка)' : 'приёмка'} товарно-материальных ценностей в следующем количестве:</p>
  <table><thead>${rows.split('</tr>')[0]}</tr></thead><tbody>${rows.split('</tr>').slice(1).join('</tr>')}</tbody></table>
  ${form.note ? `<p class="small"><b>Примечание:</b> ${escapeHtml(form.note)}</p>` : ''}
  <p class="small">Товар передан в соответствии с документом. Замечаний по количеству, качеству и комплектности: ☐ нет ☐ имеются (см. примечания).</p>
  <div class="sign">
    <div><b>Передал:</b><div class="line"></div>${isDispatch.value ? 'Кладовщик ____________ / ' + escapeHtml(form.driver || '____________') : 'Представитель поставщика ____________'}</div>
    <div><b>Принял:</b><div class="line"></div>${isDispatch.value ? 'Представитель получателя ____________' : 'Материально ответственное лицо ____________'}</div>
  </div>`;
}

async function createAct() {
  if (disabled.value) return;
  saving.value = true;
  saveError.value = '';
  try {
    const document = await persist({ ...docPayload(), issueAct: true });
    const meta = document.act;
    if (!meta?.organization || !meta?.counterparty) {
      throw new Error('Сервер не сохранил реквизиты акта. Повторите после восстановления связи.');
    }
    printHtml(meta.type + ' ' + meta.number, buildActHtml(meta));
    closeEditor();
  } catch (error) {
    saveError.value = error.message;
  } finally {
    saving.value = false;
  }
}

function exportXls() {
  downloadBlob(toXmlSpreadsheet(actRows(), form.number), `${form.number}.xls`,
    'application/vnd.ms-excel');
}
function exportCsv() {
  downloadBlob(toCsv(actRows()), `${form.number}.csv`, 'text/csv;charset=utf-8');
}
</script>

<template>
  <section :class="{ 'panel logistics-editor': inline }" :aria-labelledby="inline ? fieldId('title') : undefined">
    <h2 v-if="inline" :id="fieldId('title')" class="editor-title">{{ editorTitle }}</h2>
    <fieldset class="editor-fields" :disabled="saving || !canWrite">
    <div class="formgrid" style="margin-bottom:16px">
      <div class="field">
        <label :for="fieldId('kind')">{{ label('kind') }}</label>
        <select :id="fieldId('kind')" v-model="form.kind" class="select" :disabled="!isNew || busyLists.size > 0">
          <option v-for="(name, kind) in LOGISTICS_KINDS" :key="kind" :value="kind">{{ name }}</option>
        </select>
      </div>
      <div class="field"><label :for="fieldId('number')">{{ label('number') }}</label><input :id="fieldId('number')" v-model="form.number" class="input" placeholder="П-001"></div>
      <div class="field"><label :for="fieldId('date')">{{ label('date') }}</label><input :id="fieldId('date')" v-model="form.date" type="date" class="input"></div>
      <div class="field">
        <label :for="fieldId('status')">{{ label('status') }}</label>
        <select :id="fieldId('status')" v-model="form.status" class="select">
          <option v-if="form.status && !STATUSES.includes(form.status)" :value="form.status">{{ form.status }}</option>
          <option v-for="s in STATUSES" :key="s">{{ s }}</option>
        </select>
      </div>
      <template v-if="isDispatch">
        <CrmSelectField v-model="form.farmId" :disabled="!!shipmentId" class="field" :label="label('farmId')" :options="customers"
          searchable placeholder="Выберите клиента" @change="chooseFarm" />
        <CrmSelectField v-model="form.orderId" :disabled="!!shipmentId" class="field" :label="label('orderId')" :options="orders"
          searchable placeholder="Выберите заказ" @change="chooseOrder" />
        <div class="field">
          <label :for="fieldId('party')">{{ label('party') }}</label>
          <input :id="fieldId('party')" v-model="form.party" class="input" placeholder="Имя получателя в документе">
        </div>
      </template>
      <CrmSelectField v-else v-model="form.party" class="field" :label="label('party')" :options="suppliers"
        list-key="suppliers" searchable placeholder="Выберите поставщика" @busy-change="setListBusy('suppliers', $event)" />
      <CrmSelectField v-model="form.warehouse" class="field" :label="label('warehouse')" :options="warehouses"
        list-key="locations" searchable placeholder="Выберите склад" @busy-change="setListBusy('locations', $event)" />
      <div class="field">
        <label :for="fieldId('base')">{{ label('base') }}</label>
        <input :id="fieldId('base')" v-model="form.base" class="input" placeholder="Договор №…">
      </div>
      <template v-if="isDispatch">
        <CrmSelectField v-model="form.vehicle" class="field" :label="label('vehicle')" :options="vehicles"
          list-key="transport" searchable placeholder="Выберите автомобиль" @busy-change="setListBusy('transport', $event)" />
        <CrmSelectField v-model="form.driver" class="field" :label="label('driver')" :options="drivers"
          list-key="drivers" searchable placeholder="Выберите водителя" @busy-change="setListBusy('drivers', $event)" />
      </template>
      <div class="field full">
        <label :for="fieldId('note')">{{ label('note') }}</label>
        <textarea :id="fieldId('note')" v-model="form.note" class="textarea" rows="2"></textarea>
      </div>
    </div>

    <div class="items-heading">
      <h3>{{ label('items') }}</h3>
      <button v-if="canWrite && isDispatch && orderItems.length" class="btn slim ghost" type="button" @click="useOrderItems">
        {{ hasItems ? 'Заменить позиции из заказа' : 'Загрузить позиции из заказа' }}
      </button>
    </div>
    <div class="table-wrap" style="margin-bottom:10px">
      <table class="table items-table">
        <thead>
          <tr>
            <th style="width:26%">{{ label('skuId') }}</th>
            <th style="width:10%" class="right-h">{{ label('qty') }}</th>
            <th style="width:9%">{{ label('unit') }}</th>
            <th style="width:13%" class="right-h">{{ label('price') }}</th>
            <th style="width:14%" class="right-h">{{ label('amount') }}</th>
            <th>{{ label('note') }}</th>
            <th style="width:34px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(it, i) in form.items" :key="it.key">
            <td>
              <CrmSelectField v-if="!isRawMaterial(it) || it.skuId === PASTE.id" v-model="it.skuId" :label="label('skuId')" :options="products"
                hide-label searchable placeholder="— свободная позиция —" @change="onSku(it, $event)" />
              <input v-model="it.name" class="input slim-in" style="margin-top:4px" aria-label="Наименование" placeholder="Наименование">
              <label v-if="!isDispatch">Партия поставщика <input v-model.trim="it.lot" class="input slim-in" maxlength="200" /></label>
              <template v-if="isRawMaterial(it)">
                <span v-if="it.material === 'powder'" class="mini">Порошок (прежняя позиция)</span>
                <label>{{ label('qcStatus') }}
                  <select v-model="it.qcStatus" class="input slim-in">
                    <option>Ожидается</option><option>Пройден</option><option>Отклонён</option>
                  </select>
                </label>
              </template>
            </td>
            <td><input v-model.number="it.qty" type="number" min="0" step="0.5" class="input slim-in num-in"></td>
            <td>
              <select v-model="it.unit" class="input slim-in">
                <option v-if="it.unit && !UNITS.includes(it.unit)" :value="it.unit">{{ it.unit }}</option>
                <option v-for="u in it.skuId === PASTE.id ? ['кг'] : (isRawMaterial(it) ? ['кг', 'т'] : UNITS)" :key="u">{{ u }}</option>
              </select>
            </td>
            <td><input v-model.number="it.price" type="number" min="0" step="1" class="input slim-in num-in"></td>
            <td class="mono right"><b>{{ money(lineSum(it)) }}</b></td>
            <td><input v-model="it.note" class="input slim-in" placeholder="партия, срок…"></td>
            <td><button class="btn ghost slim danger-text" title="Удалить строку" @click="removeRow(i)">✕</button></td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td colspan="2" class="text-muted">Итого позиций: {{ form.items.length }}</td>
            <td colspan="2" class="mono right text-muted">{{ num(totalQty) }}</td>
            <td class="mono right">{{ money(totalPrice) }}</td>
            <td colspan="2"></td>
          </tr>
        </tfoot>
      </table>
    </div>

    </fieldset>
    <div class="actionbar" style="margin-bottom:14px">
      <button v-if="canWrite" class="btn slim" :disabled="saving" @click="addRow">＋ Строка</button>
      <button v-if="canWrite && !isDispatch" class="btn slim" :disabled="saving" @click="addPasteRow">＋ Партия пасты</button>
      <button class="btn slim ghost" @click="exportXls">⬇ Скачать .xls</button>
      <button class="btn slim ghost" @click="exportCsv">⬇ Скачать .csv</button>
    </div>

    <div v-if="canWrite || savedDoc?.act" class="muted-block" style="margin-bottom:16px">
      <div class="mini" style="margin-bottom:8px">
        <b>Акт под документ:</b>
        <template v-if="savedDoc?.act">
          ранее создан — {{ savedDoc.act.type }} № {{ savedDoc.act.number }} от {{ savedDoc.act.date }}.
          <span v-if="canWrite">Повторное создание перезапишет реквизиты акта.</span>
        </template>
        <template v-else>создайте акт приёма-передачи — он сохранится в карточке документа и откроется на печать (PDF).</template>
      </div>
      <div v-if="canWrite" class="actionbar">
        <button class="btn primary slim" :disabled="disabled" @click="createAct">📄 Создать акт и открыть на печать</button>
      </div>
    </div>

    <p v-if="!isDispatch && form.status === 'Принят'" class="mini">
      При сохранении принятой поставки CRM автоматически оприходует позиции на выбранном складе.
    </p>
    <div class="editor-actions">
      <button class="btn" :disabled="saving || busyLists.size > 0" @click="closeEditor">{{ canWrite ? 'Отмена' : 'Закрыть' }}</button>
      <span v-if="saveError" class="danger-text" role="alert">{{ saveError }}</span>
      <button v-if="canWrite" class="btn" :disabled="disabled" @click="save(false)">Сохранить и остаться</button>
      <button v-if="canWrite" class="btn primary" :disabled="disabled" @click="save(true)">Сохранить документ</button>
    </div>
  </section>
</template>

<style scoped>
.logistics-editor { margin-block: 12px; }
.editor-title { margin-bottom: 16px; }
.editor-fields { min-width: 0; padding: 0; margin: 0; border: 0; }
.items-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.items-heading h3 { margin: 0; }
.editor-actions { display: flex; justify-content: flex-end; align-items: center; flex-wrap: wrap; gap: 10px; }
.items-table { min-width: 690px; }
.right-h { text-align: right; }
.right { text-align: right; }
.items-table td { padding: 8px 10px; white-space: normal; }
.slim-in { padding: 7px 9px; font-size: 12px; }
.num-in { text-align: right; }
.mono { font-variant-numeric: tabular-nums; }
tfoot td { border-top: 2px solid #dfeae4; background: #fafcfb; }
</style>
