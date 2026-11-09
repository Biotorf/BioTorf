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

// Статусы пилотов — из справочника этапов (db.pilotStages), они же ENUM для status в pilots

const NUM_FIELDS = new Set(['area', 'volumeL', 'amount', 'qty', 'price', 'stock', 'primary']);
const BOOL_FIELDS = new Set(['paid']);
const LONG_FIELDS = new Set(['notes', 'text', 'route', 'result', 'tags']);

// Русские подписи коллекций и полей для модальных окон
const COLL_RU = {
  farms: 'Хозяйства', leads: 'Лиды', deals: 'Сделки', orders: 'Заказы',
  invoices: 'Счета', payments: 'Платежи', shipments: 'Отгрузки', tasks: 'Задачи',
  contacts: 'Контакты', skus: 'Товары (SKU)', warehouse: 'Склад', production: 'Производство',
  pilots: 'Пилоты', quotes: 'КП', journeys: 'Маршруты клиентов', knowledge: 'База знаний',
  media: 'Медиа', social: 'Соцсети',
};

// ── Выпадающие списки с кнопкой «＋» ────────────────────────────────
// Ключ справочника db.lists → откуда брать значения. optionsFor() объединяет
// справочник со всеми уникальными значениями поля из существующих записей,
// поэтому новые хозяйства/контакты/товары появляются в списках автоматически.
const LIST_FIELD = {
  region: 'regions', crop: 'crops', source: 'sources', owner: 'owners',
  status: 'statuses', type: 'types', stage: null, unit: 'unitPack',
  location: 'locations', transport: 'transport', driver: 'drivers',
  plate: 'plates', shift: 'shifts', operator: 'operators', platform: 'platforms',
  product: 'products', priority: 'priorities', method: 'methods', category: 'categories',
};
// Поля-ссылки на записи других таблиц (value = ID, подпись = название)
const REF_FIELD = { farmId: 'farms', dealId: 'deals', orderId: 'orders', invoiceId: 'invoices', leadId: 'leads', sku: 'skus' };
// Жёсткие перечисления (этапы воронки, приоритеты и т.п.)
const ENUM_FIELD = {
  stage: () => [...(db.data.stages || [])],
  pilotStage: () => [...(db.data.pilotStages || [])],
  priority: () => ['Низкий', 'Обычный', 'Высокий', 'Критический'],
  paid: () => ['нет', 'да'],
  primary: () => ['нет', 'да'],
  refKind: () => ['deal', 'lead', 'farm', 'order', 'invoice', 'shipment', 'pilot', 'journey', 'quote', 'task'],
  method: () => db.optionsFor('methods', 'payments', 'method'),
  category: () => db.optionsFor('categories', 'skus', 'category'),
  // статусы по коллекциям: фиксированный набор + то, что уже есть в данных
  status: () => {
    if (props.coll === 'pilots') return [...(db.data.pilotStages || [])];
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
  return k in ENUM_FIELD || k in REF_FIELD || !!LIST_FIELD[k];
}
function selectOptions(k) {
  if (k in ENUM_FIELD) return ENUM_FIELD[k]();
  if (k in REF_FIELD) {
    const coll = REF_FIELD[k];
    return (db.data[coll] || []).map((r) => ({ value: r.id, label: `${r.name || r.title || r.number || r.id} · ${r.id}` }));
  }
  return db.optionsFor(LIST_FIELD[k], props.coll, k).map((v) => ({ value: v, label: v }));
}
const FIELD_RU = {
  id: 'ID (не менять)', name: 'Название', contactName: 'Контактное лицо', phone: 'Телефон',
  company: 'Компания', region: 'Регион', source: 'Источник', owner: 'Ответственный',
  status: 'Статус', next: 'Следующее действие', notes: 'Заметки', type: 'Тип',
  crop: 'Культура', area: 'Площадь', title: 'Название / тема', farmId: 'Хозяйство (ID)',
  stage: 'Этап', volumeL: 'Объём, л', amount: 'Сумма', number: 'Номер', dealId: 'Сделка (ID)',
  date: 'Дата', orderId: 'Заказ (ID)', invoiceId: 'Счёт (ID)', paid: 'Оплачен (да/нет)',
  method: 'Способ оплаты', comment: 'Комментарий', transport: 'Транспорт', driver: 'Водитель',
  plate: 'Гос. номер', route: 'Маршрут', due: 'Срок', priority: 'Приоритет',
  refKind: 'Связь · тип', refId: 'Связь · ID', role: 'Должность', email: 'E-mail',
  primary: 'Основной контакт', sku: 'Артикул (SKU)', category: 'Категория', unit: 'Ед. изм.',
  price: 'Цена', stock: 'Остаток', batch: 'Партия', qty: 'Количество', location: 'Локация',
  expiry: 'Срок годности', product: 'Продукт', shift: 'Смена', operator: 'Оператор',
  startDate: 'Начало', endDate: 'Окончание', result: 'Результат', leadId: 'Лид (ID)',
  tags: 'Теги', text: 'Текст', url: 'Ссылка', tag: 'Метка', platform: 'Платформа',
  scheduledDate: 'Дата публикации', link: 'Ссылка',
};
function fieldLabel(k) {
  if (k === 'id') return isEdit.value ? 'ID (не менять)' : 'ID (можно оставить пустым)';
  return FIELD_RU[k] || k;
}

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
    // автопополнение выпадающих списков: регионы/культуры/ответственные из новой
    // записи попадают в справочник — в следующих таблицах они уже в списке
    for (const k of fields.value) {
      const lk = listKeyFor(k);
      if (lk && typeof rec[k] === 'string' && rec[k].trim()) db.addListItem(lk, rec[k]);
    }
    // новые хозяйства/товары автоматически становятся опциями в связанных таблицах
    if (props.coll === 'farms' && rec.name) db.addListItem('owners', rec.owner || '');
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
function quickAdd(k) {
  const lk = LIST_FIELD[k];
  const v = (adding.value[k] || '').trim();
  if (!lk || !v) return;
  db.addListItem(lk, v);
  form.value[k] = v;
  adding.value[k] = '';
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
        <label v-for="k in fields" :key="k" class="field" :class="{ wide: LONG_FIELDS.has(k) }">
          <span class="fname">{{ fieldLabel(k) }}</span>
          <!-- выпадающий список + кнопка «＋» добавления нового значения -->
          <template v-if="isSelectField(k)">
            <div class="selrow">
              <select class="input" v-model="form[k]">
                <option value="">— не выбрано —</option>
                <option v-for="o in selectOptions(k)" :key="o.value ?? o" :value="o.value ?? o">{{ o.label ?? o }}</option>
                <!-- значение может быть введено раньше и отсутствовать в списке — оставляем его -->
                <option v-if="form[k] && !selectOptions(k).some((o) => (o.value ?? o) === form[k])" :value="form[k]">{{ form[k] }} (текущее)</option>
              </select>
              <button v-if="LIST_FIELD[k]" type="button" class="btn slim plus" title="Добавить новое значение в список"
                      @click.prevent="addingOpen = addingOpen === k ? '' : k">＋</button>
            </div>
            <div v-if="LIST_FIELD[k] && addingOpen === k" class="addrow">
              <input class="input" v-model="adding[k]" placeholder="Новое значение…" @keyup.enter="quickAdd(k); addingOpen = ''" />
              <button type="button" class="btn primary slim" @click="quickAdd(k); addingOpen = ''">Добавить</button>
            </div>
          </template>
          <textarea v-else-if="LONG_FIELDS.has(k)" v-model="form[k]" rows="3"></textarea>
          <input v-else v-model="form[k]" :type="NUM_FIELDS.has(k) ? 'number' : 'text'" />
        </label>
        <div v-if="error" class="err">{{ error }}</div>
      </div>
      <div class="foot">
        <button v-if="isEdit" class="btn slim danger-text" :disabled="busy" @click="removeRecord">🗑 Удалить запись</button>
        <span style="flex:1"></span>
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
.field.wide { grid-column: 1 / -1; }
.selrow { display: flex; gap: 6px; align-items: stretch; }
.selrow select { flex: 1; border: 1px solid #cfddd5; border-radius: 8px; padding: 7px 9px; font: inherit; background: #fbfdfc; min-width: 0; }
.btn.plus { flex: none; width: 34px; padding: 0; font-size: 16px; line-height: 1; border-radius: 8px; }
.addrow { display: flex; gap: 6px; margin-top: 6px; }
.addrow .input { flex: 1; min-width: 0; }
.err { grid-column: 1 / -1; color: #c0392b; font-size: 12px; }
.foot { padding: 12px 16px; border-top: 1px solid #e3ece7; display: flex; justify-content: flex-end; gap: 8px; }
</style>
