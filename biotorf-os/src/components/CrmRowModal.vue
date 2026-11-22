<script setup>
// Ручное заполнение таблиц CRM: добавление и редактирование записи прямо из UI.
// Поля выводятся по типовому набору для коллекции (или по ключам существующих
// записей). Сохранение идёт через db.importCollection(coll, [rec], 'merge') —
// тот же путь, что и CSV-импорт: сервер + локальный кэш.
import { ref, computed, watch, onMounted } from 'vue';
import { useDbStore } from '@/stores/db';
import { COLL_RU, crmFieldLabel, REF_FIELD, REF_KINDS, crmFields, crmTitle, crmValue } from '@/data/crmFields';

const props = defineProps({
  coll: { type: String, required: true },     // farms, leads, deals…
  initialValues: { type: Object, default: () => ({}) },
  record: { type: Object, default: null },    // непусто — режим редактирования
});
const emit = defineEmits(['close', 'saved', 'deleted']);

const db = useDbStore();

const NUM_FIELDS = new Set(['area', 'volumeL', 'amount', 'qty', 'price', 'stock', 'pack', 'reserved', 'total', 'version']);
const BOOL_FIELDS = new Set(['paid', 'primary', 'received', 'public']);
const LONG_FIELDS = new Set(['notes', 'text', 'route', 'result', 'tags', 'caption']);

// ── Выпадающие списки с кнопкой «＋» ────────────────────────────────
// Ключ справочника db.lists → откуда брать значения. optionsFor() объединяет
// справочник со всеми уникальными значениями поля из существующих записей,
// поэтому новые хозяйства/контакты/товары появляются в списках автоматически.
const LIST_FIELD = {
  region: 'regions', crop: 'crops', source: 'sources', owner: 'owners',
  status: 'statuses', type: 'types', stage: null, unit: 'unitPack',
  location: 'locations', warehouse: 'locations', transport: 'transport', driver: 'drivers',
  plate: 'plates', shift: 'shifts', operator: 'operators', platform: 'platforms',
  product: 'products', priority: 'priorities', method: 'methods', category: 'categories',
};
// Жёсткие перечисления (этапы воронки, приоритеты и т.п.)
const ENUM_FIELD = {
  stage: () => [...(db.data.stages || [])],
  pilotStage: () => [...(db.data.pilotStages || [])],
  priority: () => ['Низкий', 'Обычный', 'Высокий', 'Критический'],
  consent: () => ['Нет', 'Да'],
  received: () => ['нет', 'да'],
  public: () => ['нет', 'да'],
  caseApproved: () => ['Нет', 'Да'],
  paid: () => ['нет', 'да'],
  primary: () => ['нет', 'да'],
  refKind: () => ['deal', 'lead', 'farm', 'order', 'invoice', 'shipment', 'pilot', 'journey', 'quote', 'task'],
  method: () => db.optionsFor('methods', 'payments', 'method'),
  category: () => db.optionsFor('categories', 'skus', 'category'),
  // статусы по коллекциям: фиксированный набор + то, что уже есть в данных
  status: () => {
    if (props.coll === 'pilots') return [...new Set([...(db.data.pilotStages || []), ...(db.data.pilots || []).map((p) => p.status).filter(Boolean)])];
    const base = {
      orders: ['Новый', 'Подтверждён', 'В производство', 'Готов к отгрузке', 'Оплачен', 'Отгружен', 'Отменён'],
      invoices: ['Выставлен', 'Оплачен', 'Просрочен'],
      shipments: ['Запланирована', 'В пути', 'Доставлена', 'Получено клиентом'],
      warehouse: ['В наличии', 'Зарезервировано', 'Списан'],
      production: ['План', 'В работе', 'Завершено'],
      tasks: ['Открыта', 'В работе', 'Выполнена'],
      quotes: ['Черновик', 'Отправлено', 'Принят', 'Отклонено'],
      leads: ['Новый', 'В работе', 'Квалифицирован', 'Отказ'],
      deals: [], pilots: [], social: ['Идея', 'В работе', 'Запланировано', 'Опубликовано'],
      media: [], knowledge: [], contacts: [], farms: [], skus: [],
    }[props.coll] || [];
    const seen = new Set(base);
    for (const r of db.data[props.coll] || []) {
      if (typeof r.status === 'string' && r.status.trim()) seen.add(r.status.trim());
    }
    return [...seen];
  },
};
function listKeyFor(k) { return LIST_FIELD[k]; }
function isSelectField(k) {
  return k in ENUM_FIELD || k in REF_FIELD || (k === 'refId' && !!REF_KINDS[form.value.refKind]) || !!LIST_FIELD[k];
}
function selectOptions(k) {
  if (k in ENUM_FIELD) {
    const base = ENUM_FIELD[k]();
    return LIST_FIELD[k] ? [...new Set([...base, ...db.optionsFor(LIST_FIELD[k], props.coll, k)])] : base;
  }
  if (k in REF_FIELD || k === 'refId') {
    const coll = REF_FIELD[k] || REF_KINDS[form.value.refKind];
    return (db.data[coll] || []).map((r) => ({ value: r.id, label: `${crmTitle(r)} · ${r.id}` }));
  }
  return db.optionsFor(LIST_FIELD[k], props.coll, k).map((v) => ({ value: v, label: v }));
}

function fieldLabel(key) { return crmFieldLabel(props.coll, key); }

const isEdit = computed(() => !!props.record);

const fields = computed(() => crmFields(props.coll, [props.record || props.initialValues]));
const form = ref({});
let initial = {};
const jsonFields = new Set(['history', 'qualification']);
const lineItems = ref([]);
const initialItems = ref('[]');
function addLine() {
  lineItems.value.push({ sku: '', name: '', packs: 1, unit: 'шт.', price: 0 });
}
function selectSku(item) {
  const sku = db.skuById(item.sku);
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
    f[k] = v == null ? '' : (typeof v === 'object' ? JSON.stringify(v) : String(v));
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

async function save() {
  error.value = ''; busy.value = true;
  try {
    const rec = {};
    for (const k of fields.value) {
      if (k === 'items') continue;
      let v = form.value[k];
      if (k !== 'id' && (isEdit.value ? v === initial[k] : v === '')) continue;
      if (v !== '' && NUM_FIELDS.has(k)) {
        v = Number(String(v).replace(',', '.'));
        if (!Number.isFinite(v)) throw new Error(`Введите число в поле «${fieldLabel(k)}»`);
      }
      if (v !== '' && BOOL_FIELDS.has(k)) v = /^(1|true|да|yes)$/i.test(String(v));
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
    await db.importCollection(props.coll, [rec], 'merge');
    const options = {};
    for (const k of fields.value) {
      const key = listKeyFor(k);
      if (key && typeof rec[k] === 'string' && rec[k].trim()) {
        (options[key] ??= []).push(rec[k].trim());
      }
    }
    db.mergeListOptions(options);
    emit('saved', rec);
    emit('close');
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    busy.value = false;
  }
}

// ── ручное добавление значения в справочник прямо из модалки (кнопка «＋») ──
const adding = ref({});   // field -> значение инпута
const addingOpen = ref('');  // поле, у которого открыта строка ввода нового значения
const addingBusy = ref(false);
const optionsError = ref('');

onMounted(async () => {
  try {
    await db.refreshListOptions();
  } catch {
    optionsError.value = 'Не удалось обновить общий справочник.';
  }
});

async function quickAdd(k) {
  const key = LIST_FIELD[k];
  const value = (adding.value[k] || '').trim();
  if (!key || !value || addingBusy.value || busy.value) return;
  addingBusy.value = true;
  optionsError.value = '';
  try {
    form.value[k] = await db.addListItem(key, value);
    adding.value[k] = '';
    addingOpen.value = '';
  } catch (e) {
    optionsError.value = e.message;
  } finally {
    addingBusy.value = false;
  }
}

async function removeRecord() {
  if (!props.record) return;
  const label = props.record.name || props.record.title || props.record.number || props.record.id;
  if (!confirm(`Удалить запись «${label}» из таблицы «${COLL_RU[props.coll] || props.coll}»? Это действие необратимо.`)) return;
  error.value = ''; busy.value = true;
  try {
    await db.deleteRow(props.coll, props.record.id);
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
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <div class="head">
        <b>{{ isEdit ? 'Редактировать запись' : 'Новая запись' }} · {{ COLL_RU[coll] || coll }}</b>
        <button class="x" @click="emit('close')">✕</button>
      </div>
      <div class="body">
        <fieldset v-if="fields.includes('items')" class="items wide">
          <legend>{{ fieldLabel('items') }}</legend>
          <div v-for="(item, index) in lineItems" :key="index" class="item">
            <label>{{ fieldLabel('sku') }}
              <select v-model="item.sku" class="input" @change="selectSku(item)">
                <option value="">Без артикула</option>
                <option v-if="item.sku && !db.skuById(item.sku)" :value="item.sku">{{ item.sku }}</option>
                <option v-for="sku in db.skus" :key="sku.id" :value="sku.id">{{ crmTitle(sku) }}</option>
              </select>
            </label>
            <label>Название <input v-model="item.name" class="input" /></label>
            <label>Количество <input v-model="item.packs" class="input" type="number" min="0" step="any" /></label>
            <label>Ед. изм. <input v-model="item.unit" class="input" /></label>
            <label>Цена <input v-model="item.price" class="input" type="number" min="0" step="any" /></label>
            <button type="button" class="btn slim danger-text" @click="lineItems.splice(index, 1)">Удалить позицию</button>
          </div>
          <button type="button" class="btn slim" @click="addLine">＋ Позиция</button>
        </fieldset>
        <label v-for="k in fields.filter((key) => key !== 'items')" :key="k" class="field" :class="{ wide: (LONG_FIELDS.has(k) || isJsonField(k)) }">
          <span class="fname">{{ fieldLabel(k) }}</span>
          <!-- выпадающий список + кнопка «＋» добавления нового значения -->
          <template v-if="isSelectField(k)">
            <div class="selrow">
              <select class="input" v-model="form[k]" @change="k === 'refKind' && (form.refId = '')">
                <option value="">— не выбрано —</option>
                <option v-for="o in selectOptions(k)" :key="o.value ?? o" :value="o.value ?? o">{{ o.label ?? o }}</option>
                <!-- значение может быть введено раньше и отсутствовать в списке — оставляем его -->
                <option v-if="form[k] && !selectOptions(k).some((o) => (o.value ?? o) === form[k])" :value="form[k]">{{ form[k] }} (текущее)</option>
              </select>
              <button v-if="LIST_FIELD[k]" type="button" class="btn slim plus" title="Добавить новое значение в список"
                      @click.prevent="addingOpen = addingOpen === k ? '' : k">＋</button>
            </div>
            <div v-if="LIST_FIELD[k] && addingOpen === k" class="addrow">
              <input class="input" v-model="adding[k]" placeholder="Новое значение…" maxlength="500" @keyup.enter="quickAdd(k)" />
              <button type="button" class="btn primary slim" :disabled="addingBusy || busy" @click="quickAdd(k)">Добавить</button>
            </div>
          </template>
          <textarea v-else-if="LONG_FIELDS.has(k) || isJsonField(k)" v-model="form[k]" rows="3"></textarea>
          <input v-else v-model="form[k]" :readonly="k === 'id' && isEdit" :placeholder="k === 'id' && !isEdit ? 'Можно оставить пустым' : undefined" :inputmode="NUM_FIELDS.has(k) ? 'decimal' : undefined" />
        </label>
        <div v-if="optionsError" class="err" role="alert">{{ optionsError }}</div>
        <div v-if="error" class="err">{{ error }}</div>
      </div>
      <div class="foot">
        <button v-if="isEdit" class="btn slim danger-text" :disabled="busy" @click="removeRecord">🗑 Удалить запись</button>
        <span style="flex:1"></span>
        <button class="btn ghost slim" @click="emit('close')">Отмена</button>
        <button class="btn primary slim" :disabled="busy || addingBusy" @click="save">{{ busy ? 'Сохранение…' : 'Сохранить' }}</button>
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
.wide { grid-column: 1 / -1; }
.selrow { display: flex; gap: 6px; align-items: stretch; }
.selrow select { flex: 1; border: 1px solid #cfddd5; border-radius: 8px; padding: 7px 9px; font: inherit; background: #fbfdfc; min-width: 0; }
.btn.plus { flex: none; width: 34px; padding: 0; font-size: 16px; line-height: 1; border-radius: 8px; }
.addrow { display: flex; gap: 6px; margin-top: 6px; }
.addrow .input { flex: 1; min-width: 0; }
.items { min-width: 0; border: 1px solid #cfddd5; border-radius: 8px; }
.item { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 6px; align-items: end; margin-bottom: 8px; }
.item label { min-width: 0; font-size: 12px; }
.err { grid-column: 1 / -1; color: #c0392b; font-size: 12px; }
.foot { padding: 12px 16px; border-top: 1px solid #e3ece7; display: flex; justify-content: flex-end; gap: 8px; }
</style>
