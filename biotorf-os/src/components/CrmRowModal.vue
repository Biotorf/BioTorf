<script setup>
// Ручное заполнение таблиц CRM: добавление и редактирование записи прямо из UI.
// Поля выводятся по типовому набору для коллекции (или по ключам существующих
// записей). Сохранение идёт через db.importCollection(coll, [rec], 'merge') —
// тот же путь, что и CSV-импорт: сервер + локальный кэш.
import { ref, computed, watch } from 'vue';
import { useDbStore } from '@/stores/db';

const props = defineProps({
  coll: { type: String, required: true },     // farms, leads, deals…
  record: { type: Object, default: null },    // непусто — режим редактирования
});
const emit = defineEmits(['close', 'saved']);

const db = useDbStore();

// Типовые поля коллекций (совпадают с заголовками CSV-шаблонов импорта)
const SCHEMAS = {
  farms:      ['id', 'name', 'type', 'region', 'crop', 'area', 'owner', 'status', 'next', 'phone', 'notes'],
  leads:      ['id', 'name', 'contactName', 'phone', 'company', 'region', 'source', 'owner', 'status', 'next'],
  deals:      ['id', 'title', 'farmId', 'stage', 'volumeL', 'amount', 'owner', 'next'],
  orders:     ['id', 'number', 'farmId', 'dealId', 'date', 'volumeL', 'amount', 'status', 'owner'],
  invoices:   ['id', 'number', 'orderId', 'dealId', 'date', 'amount', 'paid', 'status'],
  payments:   ['id', 'invoiceId', 'date', 'amount', 'method', 'comment'],
  shipments:  ['id', 'orderId', 'date', 'transport', 'driver', 'plate', 'route', 'status'],
  tasks:      ['id', 'title', 'owner', 'due', 'priority', 'status', 'refKind', 'refId'],
  contacts:   ['id', 'farmId', 'name', 'role', 'phone', 'email', 'primary'],
  skus:       ['id', 'name', 'category', 'unit', 'price', 'stock', 'notes'],
  warehouse:  ['id', 'sku', 'batch', 'qty', 'unit', 'location', 'expiry', 'status'],
  production: ['id', 'date', 'product', 'batch', 'qty', 'unit', 'shift', 'operator', 'notes'],
  pilots:     ['id', 'farmId', 'crop', 'area', 'startDate', 'endDate', 'status', 'owner', 'result'],
  quotes:     ['id', 'number', 'dealId', 'date', 'amount', 'status'],
  journeys:   ['id', 'leadId', 'farmId', 'stage', 'owner', 'next'],
  knowledge:  ['id', 'title', 'category', 'tags', 'text'],
  media:      ['id', 'title', 'type', 'url', 'tag', 'date'],
  social:     ['id', 'platform', 'title', 'status', 'scheduledDate', 'link'],
};

const NUM_FIELDS = new Set(['area', 'volumeL', 'amount', 'qty', 'price', 'stock', 'primary']);
const BOOL_FIELDS = new Set(['paid']);
const LONG_FIELDS = new Set(['notes', 'text', 'route', 'result', 'tags']);

const isEdit = computed(() => !!props.record);

const fields = computed(() => {
  const base = SCHEMAS[props.coll] || [];
  const keys = new Set(base);
  if (props.record) Object.keys(props.record).forEach((k) => keys.add(k));
  // если схемы нет — берём ключи из первой записи коллекции
  if (!keys.size) {
    const first = (db.data[props.coll] || [])[0];
    if (first) Object.keys(first).forEach((k) => keys.add(k));
  }
  return [...keys].filter((k) => k !== '_updatedAt');
});

const form = ref({});
function initForm() {
  const f = {};
  for (const k of fields.value) {
    const v = props.record ? props.record[k] : '';
    f[k] = v === undefined || v === null ? '' : (typeof v === 'object' ? JSON.stringify(v) : String(v));
  }
  form.value = f;
}
watch(fields, initForm, { immediate: true });

const busy = ref(false);
const error = ref('');

async function save() {
  error.value = ''; busy.value = true;
  try {
    const rec = {};
    for (const k of fields.value) {
      let v = form.value[k];
      if (v === '' || v === undefined) continue;
      if (NUM_FIELDS.has(k)) { const n = Number(String(v).replace(',', '.')); if (!Number.isNaN(n)) v = n; }
      if (BOOL_FIELDS.has(k)) v = /^(1|true|да|yes)$/i.test(String(v));
      rec[k] = v;
    }
    if (!rec.id) {
      rec.id = `${props.coll.slice(0, 2).toUpperCase()}-${String(Date.now()).slice(-8)}-${Math.floor(Math.random() * 900 + 100)}`;
    }
    await db.importCollection(props.coll, [rec], 'merge');
    emit('saved', rec);
    emit('close');
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <div class="head">
        <b>{{ isEdit ? 'Редактировать запись' : 'Новая запись' }} · {{ coll }}</b>
        <button class="x" @click="emit('close')">✕</button>
      </div>
      <div class="body">
        <label v-for="k in fields" :key="k" class="field">
          <span class="fname">{{ k === 'id' && isEdit ? 'id (не менять)' : k }}</span>
          <textarea v-if="LONG_FIELDS.has(k)" v-model="form[k]" rows="3"></textarea>
          <input v-else v-model="form[k]" :type="NUM_FIELDS.has(k) ? 'number' : 'text'" />
        </label>
        <div v-if="error" class="err">{{ error }}</div>
      </div>
      <div class="foot">
        <button class="btn ghost slim" @click="emit('close')">Отмена</button>
        <button class="btn primary slim" :disabled="busy" @click="save">{{ busy ? 'Сохранение…' : 'Сохранить' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay { position: fixed; inset: 0; background: rgba(15, 25, 20, 0.45); display: grid; place-items: center; z-index: 60; }
.modal { width: min(640px, 94vw); max-height: 86vh; display: flex; flex-direction: column; background: #ffffff; border-radius: 12px; box-shadow: 0 18px 50px rgba(10, 30, 20, 0.35); overflow: hidden; }
.head { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px; border-bottom: 1px solid #e3ece7; font-size: 14px; }
.x { border: 0; background: none; cursor: pointer; font-size: 15px; color: #6c7f76; }
.body { padding: 14px 16px; overflow: auto; display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.fname { color: #5d7168; }
.field input, .field textarea { border: 1px solid #cfddd5; border-radius: 8px; padding: 7px 9px; font: inherit; background: #fbfdfc; }
.field textarea { resize: vertical; }
.err { grid-column: 1 / -1; color: #c0392b; font-size: 12px; }
.foot { padding: 12px 16px; border-top: 1px solid #e3ece7; display: flex; justify-content: flex-end; gap: 8px; }
</style>
