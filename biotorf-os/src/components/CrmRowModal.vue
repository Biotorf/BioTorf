<script setup>
// Ручное заполнение таблиц CRM: добавление и редактирование записи прямо из UI.
// Поля выводятся по типовому набору для коллекции (или по ключам существующих
// записей). Сохранение идёт через db.importCollection(coll, [rec], 'merge') —
// тот же путь, что и CSV-импорт: сервер + локальный кэш.
import { ref, computed, watch, onMounted, nextTick, useId } from 'vue';
import { useStockWarehouses } from '@/composables/useStockWarehouses';
import CrmSelectField from '@/components/CrmSelectField.vue';
import { usePermissions } from '@/composables/usePermissions';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { COLL_RU, crmDictionaryKey, crmFieldLabel, REF_FIELD, REF_KINDS, crmFields, crmTitle, crmValue, DEAL_STAGES, dealStage, statusOptions } from '@/data/crmFields';

const { warehouses: stockWarehouses } = useStockWarehouses();

const props = defineProps({
  coll: { type: String, required: true },     // farms, leads, deals…
  initialValues: { type: Object, default: () => ({}) },
  record: { type: Object, default: null },    // непусто — режим редактирования
  inline: Boolean,
  allowReferenceCreate: { type: Boolean, default: true },
});
const emit = defineEmits(['close', 'saved', 'deleted']);

const db = useDbStore();
const ui = useUiStore();
const { canEditCollection, canSeeFarm } = usePermissions();
const modalId = useId();
const fieldId = (key) => `${modalId}-${key}`;
const heading = ref(null);

const NUM_FIELDS = new Set(['area', 'volumeL', 'amount', 'qty', 'price', 'stock', 'pack', 'reserved', 'total', 'version', 'plannedVolumeL', 'pasteUsedKg', 'powderUsedKg', 'actualQty', 'powderKgPerL', 'lossPct', 'plannedPowderKg']);
const BOOL_FIELDS = new Set(['paid', 'primary', 'received', 'public']);
const LONG_FIELDS = new Set(['notes', 'text', 'route', 'result', 'tags', 'caption']);

const requiredFields = {
  farms: ['name'], leads: ['name'], deals: ['title'], tasks: ['title'],
  contacts: ['farmId', 'name'], skus: ['name'], knowledge: ['title'],
  social: ['title'], payments: ['invoiceId', 'amount'], clientNotes: ['farmId', 'text'],
};
const boolOptions = [
  { value: 'true', label: 'Да' },
  { value: 'false', label: 'Нет' },
];
function boolValue(value) {
  return /^(1|true|да|yes)$/i.test(String(value).trim());
}

function acceptedRawLots(doc, includeLegacy = false) {
  if (doc?.kind !== 'supply' || doc.status !== 'Принят') return [];
  return [...new Set((Array.isArray(doc.items) ? doc.items : [])
    .filter((item) => (item?.material === 'powder' || (includeLegacy && item?.material === 'paste')) && item.qcStatus === 'Пройден' && item.lot)
    .map((item) => String(item.lot)))];
}
function rawLots() {
  const supply = (db.data.logistics || []).find((row) => String(row.id) === form.value.supplyId);
  return acceptedRawLots(supply, String(props.record?.supplyId) === form.value.supplyId);
}
const unitOptions = ['шт.', 'упак.', 'л', 'кг', 'т'];
const skuOptions = computed(() => db.skus.map((sku) => ({ value: String(sku.id), label: `${crmTitle(sku)} · ${sku.id}` })));
const ENUM_FIELD = {
  inputLot: () => rawLots(),
  qcStatus: () => ['Ожидается', 'Пройден', 'Отклонён'],
  stage: () => props.coll === 'deals'
    ? [...new Set([...DEAL_STAGES, ...(db.data.deals || []).map((row) => dealStage(row.stage))].filter(Boolean))]
    : [...new Set([...(db.data.stages || []), ...(db.data.journeys || []).map((row) => row.stage)].filter(Boolean))],
  pilotStage: () => [...(db.data.pilotStages || [])],
  unit: () => unitOptions,
  product: () => db.skus.map((sku) => sku.name).filter(Boolean),
  priority: () => ['Низкий', 'Средний', 'Высокий', 'Критический'],
  consent: () => ['Нет', 'Да'],
  caseApproved: () => ['Нет', 'Да'],
  refKind: () => Object.entries(REF_KINDS).map(([value, coll]) => ({ value, label: COLL_RU[coll] })),
  status: () => statusOptions(props.coll, db.data[props.coll] || [], props.coll === 'pilots' ? db.data.pilotStages : []),
};
function listKeyFor(key) {
  return crmDictionaryKey(props.coll, key);
}
function referenceTable(key) {
  if (Object.hasOwn(REF_FIELD, key)) return REF_FIELD[key];
  if (key === 'refId' && Object.hasOwn(REF_KINDS, form.value.refKind)) return REF_KINDS[form.value.refKind];
  return null;
}
function referenceRows(key) {
  const coll = referenceTable(key);
  const rows = db.data[coll] || [];
  if (key === 'supplyId') {
    return rows.filter((row) => acceptedRawLots(row, String(row.id) === String(props.record?.supplyId)).length > 0);
  }
  return rows.filter((row) => {
    const farm = coll === 'farms' ? row : (row.farmId && db.farmById(row.farmId));
    return !farm || canSeeFarm(farm);
  });
}
function isSelectField(key) {
  return key === 'warehouseId' || BOOL_FIELDS.has(key) || Object.hasOwn(ENUM_FIELD, key) || key === 'refId' || !!referenceTable(key) || !!listKeyFor(key);
}
function selectOptions(key) {
  if (key === 'warehouseId') return stockWarehouses.value.map(({id,name}) => ({ value:id, label:name }));
  if (BOOL_FIELDS.has(key)) return boolOptions;
  if (referenceTable(key)) {
    return referenceRows(key).map((r) => ({ value: String(r.id), label: `${crmTitle(r)} · ${r.id}` }));
  }
  const listKey = listKeyFor(key);
  if (Object.hasOwn(ENUM_FIELD, key)) {
    const base = ENUM_FIELD[key]();
    return listKey ? [...new Set([...base, ...db.optionsFor(listKey, props.coll, key)])] : base;
  }
  return listKey ? db.optionsFor(listKey, props.coll, key) : [];
}

function onChoiceChange(key) {
  if (key === 'refKind') form.value.refId = '';
  if (key === 'supplyId') {
    const lots = rawLots();
    form.value.inputLot = lots.length === 1 ? lots[0] : '';
  }
  if ((key === 'sku' || key === 'skuId') && form.value[key] && fields.value.includes('product')) {
    const sku = db.skus.find((row) => String(row.id) === form.value[key]);
    if (sku) form.value.product = sku.name;
  }
}
function fieldLabel(key) { return crmFieldLabel(props.coll, key); }

const linkedDraft = ref(null);
let referenceTrigger = null;
const linkedInitial = computed(() => linkedDraft.value?.coll === 'farms' ? {
  owner: ui.role === 'sales' ? (ui.login || ui.name || 'Менеджер А') : '',
} : {});

function canCreateReference(coll) {
  return props.allowReferenceCreate && ['farms', 'skus'].includes(coll) && canEditCollection(coll);
}

function createReference(coll, key, item = null) {
  if (canCreateReference(coll) && !linkedDraft.value) {
    referenceTrigger = document.activeElement;
    linkedDraft.value = { coll, key, item };
  }
}

async function closeReference() {
  linkedDraft.value = null;
  await nextTick();
  referenceTrigger?.focus();
  referenceTrigger = null;
}

function referenceSaved(record) {
  const target = linkedDraft.value;
  if (!target || !record?.id) return;
  if (target.item) {
    target.item.sku = String(record.id);
    selectSku(target.item);
  } else {
    form.value[target.key] = String(record.id);
    onChoiceChange(target.key);
  }
}

const isEdit = computed(() => !!props.record);

const fields = computed(() => crmFields(props.coll, [props.record || props.initialValues]));
const form = ref({});
const showExtraFields = ref(false);
const coreFields = {
  skus: ['id', 'name', 'line', 'pack', 'price', 'recipeVersion', 'powderKgPerL', 'lossPct'],
  production: ['date', 'warehouseId', 'sku', 'lot', 'qty', 'unit', 'plannedVolumeL', 'plannedPowderKg', 'status',
    'supplyId', 'inputLot', 'powderUsedKg', 'pasteUsedKg', 'actualQty', 'qcStatus'],
};
const visibleFields = computed(() => fields.value.filter((key) => key !== 'items' &&
  (!coreFields[props.coll] || showExtraFields.value || coreFields[props.coll].includes(key))));
const extraFieldsCount = computed(() => coreFields[props.coll] ?
  fields.value.filter((key) => !coreFields[props.coll].includes(key)).length : 0);
let initial = {};
const jsonFields = new Set(['history', 'qualification']);
const lineItems = ref([]);
const initialItems = ref('[]');
const itemKeys = new WeakMap();
let nextItemKey = 0;

function itemKey(item) {
  if (!itemKeys.has(item)) itemKeys.set(item, nextItemKey++);
  return itemKeys.get(item);
}

function addLine() {
  lineItems.value.push({ sku: '', name: '', packs: 1, unit: 'шт.', price: 0 });
}
function selectSku(item) {
  const sku = db.skus.find((row) => String(row.id) === String(item.sku));
  if (!sku) return;
  item.name = sku.name;
  item.price = sku.price ?? item.price;
  item.pack = sku.pack ?? 1;
}
function buildItems() {
  return lineItems.value.map((item) => {
    const packs = Number(item.packs);
    const price = Number(item.price);
    if ((!item.sku && !item.name?.trim()) || !Number.isFinite(packs) || packs <= 0 || !Number.isFinite(price) || price < 0) {
      throw new Error('Укажите товар, положительное количество и цену для каждой позиции.');
    }
    const pack = Number(item.pack) || db.skuById(item.sku)?.pack || 1;
    return { ...item, packs, qty: packs, price, pack, liters: packs * pack, sum: packs * price };
  });
}
function isJsonField(key) {
  const value = crmValue(props.coll, props.record, key);
  return jsonFields.has(key) || (value != null && typeof value === 'object');
}
function initForm() {
  const f = {};
  for (const k of fields.value) {
    const v = crmValue(props.coll, props.record || props.initialValues, k);
    f[k] = v == null || v === '' ? ''
      : BOOL_FIELDS.has(k) ? String(boolValue(v))
      : typeof v === 'object' ? JSON.stringify(v)
      : String(v);
  }
  const items = (props.record || props.initialValues).items;
  lineItems.value = Array.isArray(items) ? items.filter(Boolean).map((item) => ({
    ...item, sku: item.sku || item.skuId || '', packs: item.packs ?? item.qty ?? 1,
    price: item.price ?? 0, unit: item.unit || 'шт.',
  })) : [];
  initialItems.value = JSON.stringify(lineItems.value);
  initial = f;
  form.value = { ...f };
}
watch(fields, initForm, { immediate: true });

const busy = ref(false);
const error = ref('');
const pendingOptions = ref(new Set());
const addingBusy = computed(() => pendingOptions.value.size > 0);

function setDictionaryBusy(key, saving) {
  if (saving) pendingOptions.value.add(key);
  else pendingOptions.value.delete(key);
}

onMounted(() => {
  if (props.inline) {
    heading.value?.focus({ preventScroll: true });
    heading.value?.scrollIntoView({ block: 'nearest' });
  }
});

async function save() {
  if (busy.value || addingBusy.value || linkedDraft.value) return;
  error.value = ''; busy.value = true;
  try {
    const rec = {};
    if (props.coll === 'production' && form.value.status === 'Завершено' && !form.value.lot?.trim() &&
        (!isEdit.value || form.value.status !== initial.status || form.value.lot !== initial.lot)) {
      throw new Error('Укажите номер партии готовой продукции.');
    }
    const suppliedId = form.value.id?.trim();
    if (!isEdit.value && suppliedId && (db.data[props.coll] || []).some((row) => String(row.id) === suppliedId)) {
      throw new Error('Запись с таким ID уже существует. Откройте её для редактирования.');
    }
    for (const key of requiredFields[props.coll] || []) {
      if ((!isEdit.value || form.value[key] !== initial[key]) && !form.value[key]?.trim()) {
        throw new Error(`Заполните поле «${fieldLabel(key)}»`);
      }
    }
    if (props.coll === 'tasks' && (!isEdit.value || form.value.refKind !== initial.refKind || form.value.refId !== initial.refId)) {
      if (!!form.value.refKind !== !!form.value.refId) throw new Error('Укажите тип связи и выберите связанную запись.');
    }
    if (props.coll === 'production') {
      const { supplyId, inputLot, status, qcStatus, plannedVolumeL, actualQty, powderUsedKg, pasteUsedKg } = form.value;
      const linkedSupply = (db.data.logistics || []).find((row) => String(row.id) === supplyId);
      const isLegacyLot = linkedSupply?.items?.some((item) => item.lot === inputLot && item.material === 'paste')
        && !linkedSupply?.items?.some((item) => item.lot === inputLot && item.material === 'powder');
      const actualUsed = isLegacyLot ? pasteUsedKg : powderUsedKg;
      const changed = (...keys) => !isEdit.value || keys.some((key) => form.value[key] !== initial[key]);
      const validLot = !!supplyId && !!inputLot && rawLots().includes(inputLot);
      if (changed('supplyId', 'inputLot') && (supplyId || inputLot) && !validLot) {
        throw new Error('Выберите принятую поставку сырья и партию, прошедшую контроль качества.');
      }
      const finishing = status === 'Завершено' && Number(String(plannedVolumeL).replace(',', '.')) > 0
        && changed('status', 'qcStatus', 'plannedVolumeL', 'actualQty', 'pasteUsedKg', 'powderUsedKg', 'supplyId', 'inputLot');
      if (finishing && (
        !validLot || !(Number(String(actualQty).replace(',', '.')) > 0) ||
        !(Number(String(actualUsed).replace(',', '.')) > 0) || !['Пройден', 'Отклонён'].includes(qcStatus)
      )) {
        throw new Error('Для завершения партии укажите принятую партию сырья, фактический выпуск, расход сырья и результат контроля качества.');
      }
    }
    if (props.coll === 'skus') {
      const { recipeVersion, powderKgPerL, lossPct } = form.value;
      if ((powderKgPerL !== '' || lossPct !== '') && (
        !recipeVersion?.trim() || !(Number(powderKgPerL.replace(',', '.')) > 0) ||
        lossPct === '' || !(Number(lossPct.replace(',', '.')) >= 0 && Number(lossPct.replace(',', '.')) < 100)
      )) throw new Error('Для расчёта сырья укажите версию рецептуры, норму порошка больше нуля и потери от 0 до 100% (исключительно).');
    }
    for (const k of fields.value) {
      if (k === 'items' || (k === 'stage' && props.coll === 'deals' && props.record?.journeyId)) continue;
      let v = form.value[k];
      if (k !== 'id' && (isEdit.value ? v === initial[k] : v === '')) continue;
      if (referenceTable(k) && v && !referenceRows(k).some((row) => String(row.id) === v)) {
        throw new Error(`Выберите существующую запись в поле «${fieldLabel(k)}»`);
      }
      if (v !== '' && NUM_FIELDS.has(k)) {
        v = Number(String(v).trim().replace(',', '.'));
        if (!Number.isFinite(v) || v < 0) throw new Error(`Введите неотрицательное число в поле «${fieldLabel(k)}»`);
        if (props.coll === 'payments' && k === 'amount' && v === 0) throw new Error('Сумма платежа должна быть больше нуля.');
      }
      if (v !== '' && BOOL_FIELDS.has(k)) v = boolValue(v);
      if (isJsonField(k)) {
        try {
          v = v === '' ? (['items', 'history'].includes(k) ? [] : null) : JSON.parse(v);
          if (['items', 'history'].includes(k) && !Array.isArray(v)) throw new Error();
        } catch {
          throw new Error(`Проверьте формат JSON в поле «${fieldLabel(k)}»`);
        }
      }
      rec[k] = v;
    }
    if (fields.value.includes('items') && (!isEdit.value || JSON.stringify(lineItems.value) !== initialItems.value)) {
      rec.items = buildItems();
      const total = rec.items.reduce((sum, item) => sum + item.sum, 0);
      if (props.coll === 'quotes') rec.total = total;
      if (props.coll === 'orders' && rec.amount == null) rec.amount = total;
    }
    if (props.record?._updatedAt) rec._expectedRev = props.record._updatedAt;
    if (!isEdit.value && !rec.id?.trim()) rec.id = db.uid(props.coll);
    const isInvoice = props.coll === 'invoices';
    const result = await db.importCollection(props.coll, [rec], 'merge', isInvoice);
    if (isInvoice && db.serverOnline) await db.pullCrmState();
    emit('saved', result?.records?.[0] || rec);
    emit('close');
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    busy.value = false;
  }
}

async function removeRecord() {
  if (!props.record) return;
  const label = props.record.name || props.record.title || props.record.number || props.record.id;
  if (!confirm(`Удалить запись «${label}» из таблицы «${COLL_RU[props.coll] || props.coll}»? Это действие необратимо.`)) return;
  error.value = ''; busy.value = true;
  try {
    await db.deleteRow(props.coll, props.record.id);
    if (props.coll === 'invoices' && db.serverOnline) await db.pullCrmState();
    emit('deleted', props.record.id);
    emit('close');
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div :class="inline ? 'inline-wrap' : 'overlay'" @click.self="!inline && !busy && !addingBusy && !linkedDraft && emit('close')">
    <section :class="inline ? 'panel inline-editor' : 'modal'" :role="inline ? undefined : 'dialog'"
      :aria-modal="inline ? undefined : 'true'" :aria-labelledby="modalId">
      <div class="head">
        <h2 :id="modalId" ref="heading" tabindex="-1">{{ isEdit ? 'Редактировать запись' : 'Новая запись' }} · {{ COLL_RU[coll] || coll }}</h2>
        <button class="x" type="button" aria-label="Закрыть форму" :disabled="busy || addingBusy || !!linkedDraft" @click="emit('close')">✕</button>
      </div>
      <div class="body">
        <fieldset v-if="fields.includes('items')" class="items wide">
          <legend>{{ fieldLabel('items') }}</legend>
          <div v-for="(item, index) in lineItems" :key="itemKey(item)" class="item">
            <CrmSelectField v-model="item.sku" :label="fieldLabel('sku')" :options="skuOptions" searchable
              placeholder="Без артикула" :disabled="busy || !!linkedDraft" :allow-create="canCreateReference('skus')"
              @change="selectSku(item)" @create-request="createReference('skus', 'items', item)" />
            <label>Название <input v-model="item.name" class="input" /></label>
            <label>Количество <input v-model="item.packs" class="input" type="number" min="0" step="any" /></label>
            <CrmSelectField v-model="item.unit" :label="fieldLabel('unit')" :options="unitOptions" list-key="unitPack"
              :disabled="busy || !!linkedDraft" @busy-change="setDictionaryBusy(item, $event)" />
            <label>Цена <input v-model="item.price" class="input" type="number" min="0" step="any" /></label>
            <button type="button" class="btn slim danger-text" :disabled="busy || addingBusy || !!linkedDraft"
              @click="lineItems.splice(index, 1)">Удалить позицию</button>
          </div>
          <button type="button" class="btn slim" :disabled="busy || !!linkedDraft" @click="addLine">＋ Позиция</button>
        </fieldset>
        <div v-for="k in visibleFields" :key="k" class="field" :class="{ wide: (LONG_FIELDS.has(k) || isJsonField(k)) }">
          <label class="fname" :for="fieldId(k)">{{ fieldLabel(k) }}</label>
          <CrmSelectField v-if="isSelectField(k)" :id="fieldId(k)" v-model="form[k]" :label="fieldLabel(k)"
            hide-label searchable :options="selectOptions(k)" :list-key="listKeyFor(k)" :allow-create="canCreateReference(referenceTable(k))"
            :disabled="busy || !!linkedDraft || (k === 'stage' && coll === 'deals' && !!record?.journeyId) || (k === 'refId' && !referenceTable(k))"
            @change="onChoiceChange(k)" @create-request="createReference(referenceTable(k), k)" @busy-change="setDictionaryBusy(k, $event)" />
          <textarea v-else-if="LONG_FIELDS.has(k) || isJsonField(k)" :id="fieldId(k)" v-model="form[k]" rows="3"></textarea>
          <input v-else :id="fieldId(k)" v-model="form[k]" :readonly="(k === 'id' && isEdit) || (coll === 'production' && k === 'plannedPowderKg')" :placeholder="k === 'id' && !isEdit ? 'Можно оставить пустым' : undefined" :inputmode="NUM_FIELDS.has(k) ? 'decimal' : undefined" />
        </div>
        <div v-if="extraFieldsCount" class="wide">
          <button type="button" class="btn slim ghost" :disabled="addingBusy || !!linkedDraft" :aria-expanded="showExtraFields" @click="showExtraFields = !showExtraFields">
            {{ showExtraFields ? 'Скрыть дополнительные поля' : 'Дополнительные поля' }}
          </button>
        </div>
        <CrmRowModal v-if="linkedDraft" inline class="wide linked-editor" :coll="linkedDraft.coll" :key="linkedDraft.coll"
          :initial-values="linkedInitial" :allow-reference-create="false" @saved="referenceSaved" @close="closeReference" />
        <div v-if="error" class="err" role="alert">{{ error }}</div>
      </div>
      <div class="foot">
        <button v-if="isEdit" type="button" class="btn slim danger-text remove" :disabled="busy || addingBusy || !!linkedDraft" @click="removeRecord">🗑 Удалить запись</button>
        <button type="button" class="btn ghost slim" :disabled="busy || addingBusy || !!linkedDraft" @click="emit('close')">Отмена</button>
        <button type="button" class="btn primary slim" :disabled="busy || addingBusy || !!linkedDraft" @click="save">{{ busy ? 'Сохранение…' : 'Сохранить' }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.overlay { position: fixed; inset: 0; background: rgba(15, 25, 20, 0.45); display: grid; place-items: center; z-index: 60; }
.modal { width: min(640px, 94vw); max-height: 86vh; display: flex; flex-direction: column; background: #ffffff; border-radius: 12px; box-shadow: 0 18px 50px rgba(10, 30, 20, 0.35); overflow: hidden; }
.inline-wrap { min-width: 0; margin: 12px 0; }
.inline-editor { padding: 0; background: var(--panel, #ffffff); }
.linked-editor { margin: 6px 0; }
.linked-editor :deep(.inline-editor) { border-color: #8ab2a0; }
.head { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px; border-bottom: 1px solid #e3ece7; font-size: 14px; }
.head h2 { margin: 0; font-size: 15px; }
.x { border: 0; background: none; cursor: pointer; font-size: 15px; color: #6c7f76; }
.body { padding: 14px 16px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 14px; }
.modal > .body { overflow: auto; }
.field { display: flex; flex-direction: column; gap: 4px; min-width: 0; font-size: 12px; }
.fname { color: #5d7168; }
.field input, .field textarea { border: 1px solid #cfddd5; border-radius: 8px; padding: 7px 9px; font: inherit; background: #fbfdfc; }
.field textarea { resize: vertical; }
.wide { grid-column: 1 / -1; }
.items { min-width: 0; border: 1px solid #cfddd5; border-radius: 8px; }
.item { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 6px; align-items: end; margin-bottom: 8px; font-size: 12px; }
.item label { min-width: 0; }
.item label .input { width: 100%; }
.err { grid-column: 1 / -1; color: #c0392b; font-size: 12px; }
.foot { padding: 12px 16px; border-top: 1px solid #e3ece7; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.remove { margin-right: auto; }
@media (max-width: 580px) {
  .body { grid-template-columns: minmax(0, 1fr); }
}
</style>
