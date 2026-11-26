<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { stock } from '@/api/stockClient';
import { useDbStore } from '@/stores/db';
import { usePermissions } from '@/composables/usePermissions';
import CrmDataTable from '@/components/CrmDataTable.vue';
import InventoryLedger from '@/components/InventoryLedger.vue';
import ManualLink from '@/components/ui/ManualLink.vue';

const db = useDbStore();
const { canEdit } = usePermissions();
const writable = computed(() => canEdit('warehouse'));
const productionOnly = computed(() => !writable.value && canEdit('production'));
const canWriteDocument = (entry) => writable.value || productionOnly.value && entry?.doc_type === 'production';
const kinds = { purchase:'Приход', sale:'Продажа', move:'Перемещение', writeoff:'Списание',
  production:'Производство', inventory:'Инвентаризация', return:'Возврат' };
const statuses = { draft:'Черновик', conducted:'Проведён', cancelled:'Отменён' };
const types = { raw:'Сырьё', packaging:'Тара', finished:'Готовый товар', service:'Услуга' };
const tabs = { balances:'Остатки', documents:'Документы', movements:'Журнал', turnover:'Обороты',
  reservations:'Резервы', products:'Товары', warehouses:'Склады', recipes:'Техкарты' };
const tab = ref('balances');
const rows = ref([]);
const products = ref([]);
const warehouses = ref([]);
const recipes = ref([]);
const draft = ref(null);
const capacity = ref(null);
const itemBalances = ref([]);
const movementPage = ref(0);
const pageLength = 100;
const pending = ref(false);
const archiveOpen = ref(false);
const error = ref('');
const warning = ref('');
const filters = ref({ warehouse_id:'', product_id:'', date_from:'', date_to:'' });
let queryVersion = 0;
const item = () => ({ product_id:'', qty:'', unit_cost:'' });
const component = () => ({ component_product_id:'', warehouse_id:'raw', qty_per_unit_output:'' });
const catalog = (key) => ['products','warehouses','recipes'].includes(key);
const path = (key) => '/stock/' + (catalog(key) ? 'catalog/' : '') + key;
const label = (list, id) => list.find((row) => row.id === id)?.name || id || '—';
const selectedProduct = computed(() => products.value.find((row) => row.id === filters.value.product_id));
const alerts = computed(() => tab.value === 'balances' ? rows.value.filter((row) => row.low) : []);

async function refresh() {
  const selected = tab.value;
  const version = ++queryVersion;
  try {
    const query = new URLSearchParams();
    if (['balances','movements','turnover'].includes(selected)) {
      for (const [key, value] of Object.entries(filters.value)) if (value) query.set(key, value);
    }
    if (['documents','reservations'].includes(selected) && filters.value.warehouse_id) query.set('warehouse_id', filters.value.warehouse_id);
    if (selected === 'movements') {
      query.set('limit', pageLength);
      query.set('offset', movementPage.value * pageLength);
    }
    const result = await stock(path(selected) + (query.size ? '?' + query : ''));
    if (version === queryVersion) rows.value = result;
    if (selected === 'movements' && filters.value.product_id) {
      const balances = await stock('/stock/balances?' + new URLSearchParams({product_id: filters.value.product_id}));
      if (version === queryVersion) itemBalances.value = balances.filter((row) => Number(row.qty) || row.low);
    } else if (version === queryVersion) itemBalances.value = [];
  } catch (e) { if (version === queryVersion) error.value = e.message; }
}
async function loadCatalogs() {
  [products.value, warehouses.value, recipes.value] = await Promise.all(
    ['products','warehouses','recipes'].map((key) => stock(path(key))));
}
function navigate(key) {
  movementPage.value = 0;
  tab.value = key; rows.value = []; draft.value = null; capacity.value = null; error.value = ''; warning.value = '';
  return refresh();
}
function refreshFilters() { movementPage.value = 0; return refresh(); }
function emptyDraft(key) {
  const chosen = filters.value.warehouse_id;
  if (key === 'products') return { sku:'', name:'', type:'finished', unit:'шт', min_stock_alert:'0' };
  if (key === 'warehouses') return { name:'', is_virtual:false, allow_negative:false };
  if (key === 'recipes') return { output_product_id:'', version:'1', output_qty_per_batch:'1', is_active:true, items:[component()] };
  if (key === 'reservations') return { product_id:'', warehouse_id:chosen || 'finished', order_id:'', qty:'', expires_at:'' };
  return { doc_type:productionOnly.value ? 'production' : 'purchase', number:'', warehouse_from_id:'', warehouse_to_id:chosen || (productionOnly.value ? 'finished' : 'raw'), recipe_id:'',
    order_id:'', counterparty_id:'', items:[item()] };
}
function changeType() {
  const form = draft.value;
  form.warehouse_from_id = ['sale','move','writeoff'].includes(form.doc_type) ? 'finished' : '';
  form.warehouse_to_id = ({ purchase:'raw', return:'finished', production:'finished', inventory:'finished', move:'raw' })[form.doc_type] || '';
  const chosen = filters.value.warehouse_id;
  if (chosen && form.warehouse_from_id) form.warehouse_from_id = chosen;
  if (chosen && form.warehouse_to_id) {
    form.warehouse_to_id = chosen === form.warehouse_from_id ? '' : chosen;
  }
  form.recipe_id = '';
}
function selectRecipe() {
  const recipe = recipes.value.find(({id}) => id === draft.value.recipe_id);
  if (recipe) draft.value.items = [{...item(), product_id:recipe.output_product_id, qty:recipe.output_qty_per_batch}];
}
async function action(run) {
  if (pending.value) return;
  pending.value = true; error.value = '';
  try { await run(); }
  catch(e) { error.value = e.message; }
  finally { pending.value = false; }
}
function saveDraft() {
  const key = tab.value;
  const form = {...draft.value};
  action(async () => {
    if (key === 'reservations' && form.expires_at) form.expires_at = new Date(form.expires_at).toISOString();
    if (key === 'products' && !form.id && form.crmSku) {
      await stock('/stock/import-sku/' + encodeURIComponent(form.crmSku), 'POST', form);
    } else {
      await stock(path(key) + (form.id ? '/' + form.id : ''), form.id ? 'PUT' : 'POST', form);
    }
    draft.value = null;
    if (catalog(key)) await loadCatalogs();
    await refresh();
  });
}
async function openDocument(row) {
  await action(async () => { draft.value = await stock(path('documents') + '/' + row.id); });
}
function editReservation(row) {
  const date = new Date(row.expires_at);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  draft.value = {...row, expires_at:local.toISOString().slice(0,16)};
}
function deleteDocument(row) {
  if (!confirm(`Удалить черновик «${row.number}»?`)) return;
  action(async () => {
    await stock(path('documents') + '/' + row.id, 'DELETE');
    if (draft.value?.id === row.id) draft.value = null;
    await refresh();
  });
}
function operate(row, verb) {
  if (verb === 'cancel' && !confirm('Отменить документ? Для проведённого документа будет записано сторно.')) return;
  action(async () => {
    await stock(path('documents') + '/' + row.id + '/' + verb, 'POST');
    draft.value = null;
    await refresh();
  });
}
function remove(row) {
  if (!confirm(tab.value === 'reservations' ? 'Снять резерв?' : 'Удалить запись справочника?')) return;
  action(async () => {
    await stock(path(tab.value) + '/' + row.id, 'DELETE');
    if (catalog(tab.value)) await loadCatalogs();
    await refresh();
  });
}
function productHistory(row) {
  filters.value = { warehouse_id:row.warehouse_id, product_id:row.product_id, date_from:'', date_to:'' };
  navigate('movements');
}
function openRecipe(row) {
  action(async () => { capacity.value = await stock('/recipes/' + row.id + '/can_produce'); });
}
async function routeDraft() {
  const route = new URLSearchParams(location.hash.split('?')[1]);
  const mode = route.get('movement');
  if (!mode || (!writable.value && !(productionOnly.value && mode === 'production'))) return;
  const basis = route.get('sourceId');
  const collection = route.get('sourceCollection');
  await navigate(mode === 'reserve' ? 'reservations' : 'documents');
  draft.value = emptyDraft(tab.value);
  if (mode !== 'reserve') {
    draft.value.doc_type = ({ production:'production', dispatch:'sale', receipt_powder:'purchase',
      receipt_finished:'purchase', shipment:'sale' })[mode] || 'purchase';
    changeType();
    if (basis) { draft.value.source_id = basis; draft.value.source_collection = collection; }
  }
  draft.value.order_id = route.get('orderId') || (collection === 'orders' ? basis : '') || '';
  const source = db.data[collection]?.find((row) => row.id === basis);
  if (source && mode === 'production') {
    const product = products.value.find((row) => row.sku === source.sku);
    const recipe = recipes.value.find((row) => row.is_active && row.output_product_id === product?.id);
    if (recipe) {
      draft.value.recipe_id = recipe.id;
      selectRecipe();
      if (product.unit === 'шт' && source.actualQty) draft.value.items[0].qty = String(source.actualQty);
    }
  }
  if (source && ['dispatch','reserve'].includes(mode)) {
    const lines = (source.items?.length ? source.items : [source]).map((line) => {
      const product = products.value.find((row) => row.sku === (line.skuId || line.sku) && row.unit === 'шт');
      return product && {...item(), product_id:product.id, qty:String(line.packs ?? line.qty ?? '')};
    }).filter(Boolean);
    if (mode === 'reserve' && lines.length === 1) Object.assign(draft.value, lines[0]);
    if (mode === 'dispatch' && lines.length) draft.value.items = lines;
  }
  const sourceWarehouse = source?.warehouseId || warehouses.value.find((row) => row.name === source?.warehouse)?.id;
  if (sourceWarehouse) {
    const field = mode === 'reserve' ? 'warehouse_id' : mode === 'dispatch' ? 'warehouse_from_id' : 'warehouse_to_id';
    draft.value[field] = sourceWarehouse;
    filters.value.warehouse_id = sourceWarehouse;
    await refresh();
  }
  draft.value.counterparty_id = source?.farmId || '';
  warning.value = basis ? 'Основание CRM: ' + basis + '. Сверьте товары, количества и склады перед проведением.' : '';
}
onMounted(async () => {
  await action(async () => { await loadCatalogs(); await refresh(); });
  await routeDraft();
  window.addEventListener('hashchange', routeDraft);
});
onUnmounted(() => window.removeEventListener('hashchange', routeDraft));
</script>

<template>
  <section>
    <header class="pagehead"><div><h1>Склад</h1><ManualLink /><p class="subtitle">Документы, резервы и себестоимость</p></div></header>
    <nav class="actionbar stock-nav" aria-label="Разделы склада">
      <button v-for="(name,key) in tabs" :key="key" class="btn slim" :class="{ primary:tab===key }" :aria-pressed="tab===key" :disabled="pending" @click="navigate(key)">{{name}}</button>
    </nav>
    <p v-if="error" role="alert" class="danger-text">{{error}}</p>
    <p v-if="warning" class="note">{{warning}}</p>
    <p v-if="alerts.length" role="status" class="note">Ниже минимального остатка: {{alerts.map(row => row.product + ' · ' + row.warehouse).join(', ')}}</p>
    <div v-if="['balances','movements','turnover','documents','reservations'].includes(tab)" class="toolbar" data-tour="warehouse-balance">
      <label>Склад <select aria-label="Фильтр по складу" v-model="filters.warehouse_id" class="select" @change="refreshFilters"><option value="">Все склады</option><option v-for="w in warehouses" :key="w.id" :value="w.id">{{w.name}}</option></select></label>
      <label v-if="['balances','movements','turnover'].includes(tab)">Товар <select v-model="filters.product_id" class="select" @change="refreshFilters"><option value="">Все товары</option><option v-for="p in products" :key="p.id" :value="p.id">{{p.name}}</option></select></label>
      <template v-if="['movements','turnover'].includes(tab)">
        <label>С даты <input v-model="filters.date_from" type="date" class="input" @change="refreshFilters" /></label>
        <label>До даты, исключая <input v-model="filters.date_to" type="date" class="input" @change="refreshFilters" /></label>
      </template>
    </div>
    <button v-if="writable && (catalog(tab) || ['documents','reservations'].includes(tab)) || productionOnly && tab==='documents'" class="btn primary stock-nav" data-tour="warehouse-post" @click="draft=emptyDraft(tab)">＋ {{tab==='documents' ? 'Новый документ' : tab==='reservations' ? 'Новый резерв' : 'Добавить'}}</button>
    <form v-if="draft" class="panel stock-form" @submit.prevent="saveDraft">
      <fieldset :disabled="pending || (tab==='documents' && draft.status && draft.status!=='draft')">
        <template v-if="tab==='documents'">
          <label>Тип <select v-model="draft.doc_type" @change="changeType"><option v-for="(name,key) in (productionOnly ? { production:kinds.production } : kinds)" :key="key" :value="key">{{name}}</option></select></label>
          <label>Номер <input v-model="draft.number" placeholder="Автоматически" /></label>
          <label v-if="['sale','move','writeoff'].includes(draft.doc_type)">Со склада <select v-model="draft.warehouse_from_id" required><option value="">Выберите склад</option><option v-for="w in warehouses" :key="w.id" :value="w.id">{{w.name}}</option></select></label>
          <label v-if="['purchase','return','move','production','inventory'].includes(draft.doc_type)">На склад <select v-model="draft.warehouse_to_id" required><option value="">Выберите склад</option><option v-for="w in warehouses" :key="w.id" :value="w.id">{{w.name}}</option></select></label>
          <label v-if="draft.doc_type==='production'">Техкарта <select v-model="draft.recipe_id" required @change="selectRecipe"><option value="">Выберите версию</option><option v-for="r in recipes" :key="r.id" :value="r.id">{{label(products,r.output_product_id)}} · {{r.version}}{{r.is_active ? ' · действующая' : ''}}</option></select></label>
          <label>Заказ CRM <select v-model="draft.order_id"><option value="">Без заказа</option><option v-for="o in db.orders" :key="o.id" :value="o.id">{{o.number || o.num || o.id}}</option></select></label>
          <label>Контрагент <select v-model="draft.counterparty_id"><option value="">Без контрагента</option><option v-for="f in db.farms" :key="f.id" :value="f.id">{{f.name}}</option></select></label>
          <div v-for="(line,index) in draft.items" :key="index" class="stock-line">
            <label>Товар <select v-model="line.product_id" aria-label="Товар" required><option value="">Выберите товар</option><option v-for="p in products.filter(row=>row.type!=='service')" :key="p.id" :value="p.id">{{p.name}} · {{p.unit}}</option></select></label>
            <label>{{draft.doc_type==='inventory' ? 'Фактически' : 'Количество'}} <input v-model="line.qty" type="number" min="0" step="0.0001" required /></label>
            <label v-if="['purchase','return','inventory'].includes(draft.doc_type)">Себестоимость единицы <input v-model="line.unit_cost" type="number" min="0" step="0.0001" :required="draft.doc_type!=='inventory'" /></label>
            <button v-if="draft.items.length>1" class="btn slim" type="button" @click="draft.items.splice(index,1)">Убрать</button>
          </div>
          <button v-if="draft.doc_type!=='production'" class="btn slim" type="button" @click="draft.items.push(item())">＋ Позиция</button>
        </template>
        <template v-if="tab==='products'">
          <label v-if="!draft.id">Из каталога CRM <select v-model="draft.crmSku"><option value="">Создать вручную</option><option v-for="s in db.skus" :key="s.id" :value="s.id">{{s.name}}</option></select></label>
          <template v-if="!draft.crmSku"><label>Артикул <input v-model="draft.sku" required /></label><label>Название <input v-model="draft.name" required /></label></template>
          <label>Тип <select v-model="draft.type"><option v-for="(name,key) in types" :key="key" :value="key">{{name}}</option></select></label>
          <label>Единица <select v-model="draft.unit"><option>шт</option><option>кг</option><option>л</option></select></label>
          <label>Минимальный остаток <input v-model="draft.min_stock_alert" type="number" min="0" step="0.0001" required /></label>
        </template>
        <template v-if="tab==='warehouses'">
          <label>Название <input v-model="draft.name" required /></label>
          <label class="stock-check"><input v-model="draft.is_virtual" type="checkbox" /> Виртуальный</label>
          <label class="stock-check"><input v-model="draft.allow_negative" type="checkbox" /> Допускать отрицательные остатки</label>
        </template>
        <template v-if="tab==='recipes'">
          <label>Готовый товар <select v-model="draft.output_product_id" required><option value="">Выберите</option><option v-for="p in products.filter(row=>row.type==='finished')" :key="p.id" :value="p.id">{{p.name}}</option></select></label>
          <label>Версия <input v-model="draft.version" required /></label>
          <label>Выпуск за партию <input v-model="draft.output_qty_per_batch" type="number" min="0.0001" step="0.0001" required /></label>
          <label class="stock-check"><input v-model="draft.is_active" type="checkbox" /> Действующая версия</label>
          <div v-for="(line,index) in draft.items" :key="index" class="stock-line">
            <label>Компонент <select v-model="line.component_product_id" required><option value="">Выберите</option><option v-for="p in products.filter(row=>['raw','packaging'].includes(row.type))" :key="p.id" :value="p.id">{{p.name}} · {{p.unit}}</option></select></label>
            <label>Склад компонента <select v-model="line.warehouse_id" required><option v-for="w in warehouses" :key="w.id" :value="w.id">{{w.name}}</option></select></label>
            <label>На единицу выпуска <input v-model="line.qty_per_unit_output" type="number" min="0.0001" step="0.0001" required /></label>
            <button v-if="draft.items.length>1" type="button" class="btn slim" @click="draft.items.splice(index,1)">Убрать</button>
          </div>
          <button type="button" class="btn slim" @click="draft.items.push(component())">＋ Компонент</button>
        </template>
        <template v-if="tab==='reservations'">
          <label>Товар <select v-model="draft.product_id" required><option value="">Выберите</option><option v-for="p in products.filter(row=>row.type!=='service')" :key="p.id" :value="p.id">{{p.name}}</option></select></label>
          <label>Склад <select v-model="draft.warehouse_id" required><option v-for="w in warehouses" :key="w.id" :value="w.id">{{w.name}}</option></select></label>
          <label>Заказ <select v-model="draft.order_id" required><option value="">Выберите заказ</option><option v-for="o in db.orders" :key="o.id" :value="o.id">{{o.number || o.num || o.id}}</option></select></label>
          <label>Количество <input v-model="draft.qty" type="number" min="0.0001" step="0.0001" required /></label>
          <label>Действует до <input v-model="draft.expires_at" type="datetime-local" required /></label>
        </template>
      </fieldset>
      <div class="actionbar">
        <button class="btn slim" type="button" @click="draft=null">Закрыть</button>
        <button v-if="(tab==='documents' ? canWriteDocument(draft) : writable) && (!draft.status || draft.status==='draft')" type="submit" class="btn primary" :disabled="pending">{{tab==='documents' ? 'Сохранить черновик' : 'Сохранить'}}</button>
      </div>
    </form>
    <p v-if="capacity" class="note">Можно выпустить {{capacity.qty}} единиц. Полных партий: {{capacity.batches}}.</p>
    <p v-if="tab==='movements' && selectedProduct" class="subtitle">Карточка товара · {{selectedProduct.name}}</p>
    <ul v-if="tab==='movements' && selectedProduct && itemBalances.length"><li v-for="row in itemBalances" :key="row.warehouse_id">{{row.warehouse}} · {{row.qty}} {{row.unit}} · себестоимость {{row.unit_cost}} сом за единицу</li></ul>
    <div class="table-wrap">
      <table class="table">
        <thead><tr>
          <template v-if="tab==='balances'"><th>Товар</th><th>Склад</th><th>Остаток</th><th>Резерв</th><th>Доступно</th><th>Себестоимость за единицу</th></template>
          <template v-else-if="tab==='documents'"><th>Номер</th><th>Тип</th><th>Со склада</th><th>На склад</th><th>Статус</th><th>Действия</th></template>
          <template v-else-if="tab==='movements'"><th>Дата</th><th>Товар</th><th>Склад</th><th>Количество</th><th>Себестоимость</th><th>Документ</th></template>
          <template v-else-if="tab==='turnover'"><th>Товар</th><th>Склад</th><th>Приход</th><th>Расход</th></template>
          <template v-else-if="tab==='reservations'"><th>Товар</th><th>Склад</th><th>Заказ</th><th>Осталось</th><th>Срок</th><th>Действия</th></template>
          <template v-else><th>Название</th><th>Сведения</th><th>Действия</th></template>
        </tr></thead>
        <tbody><tr v-for="row in rows" :key="row.id || row.warehouse_id+':'+row.product_id">
          <template v-if="tab==='balances'"><td><button class="btn slim ghost" @click="productHistory(row)">{{row.product}}</button></td><td>{{row.warehouse}}</td><td>{{row.qty}} {{row.unit}}</td><td>{{row.reserved}}</td><td :class="{'danger-text':row.low}">{{row.available}}</td><td>{{row.unit_cost}}</td></template>
          <template v-else-if="tab==='documents'"><td><button class="btn slim ghost" @click="openDocument(row)">{{row.number}}</button></td><td>{{kinds[row.doc_type]}}</td><td>{{label(warehouses,row.warehouse_from_id)}}</td><td>{{label(warehouses,row.warehouse_to_id)}}</td><td>{{statuses[row.status]}}</td><td class="actionbar"><button v-if="canWriteDocument(row) && row.status==='draft'" class="btn primary slim" :disabled="pending || !!draft" @click="operate(row,'conduct')">Провести</button><button v-if="canWriteDocument(row) && row.status!=='cancelled'" class="btn slim" :disabled="pending" @click="operate(row,'cancel')">{{row.status==='conducted' ? 'Сторно' : 'Отменить'}}</button><button v-if="canWriteDocument(row) && row.status==='draft'" class="btn slim" :disabled="pending" @click="openDocument(row)">Изменить</button><button v-if="canWriteDocument(row) && row.status==='draft'" class="btn slim ghost danger-text" :disabled="pending" @click="deleteDocument(row)">Удалить</button></td></template>
          <template v-else-if="tab==='movements'"><td>{{new Date(row.moved_at).toLocaleString('ru')}}</td><td>{{label(products,row.product_id)}}</td><td>{{label(warehouses,row.warehouse_id)}}</td><td>{{row.qty}}</td><td>{{row.unit_cost}}</td><td>{{row.reversal_of ? 'Сторно · ' : ''}}{{row.document_id}}</td></template>
          <template v-else-if="tab==='turnover'"><td>{{label(products,row.product_id)}}</td><td>{{label(warehouses,row.warehouse_id)}}</td><td>{{row.receipt}}</td><td>{{row.issue}}</td></template>
          <template v-else-if="tab==='reservations'"><td>{{label(products,row.product_id)}}</td><td>{{label(warehouses,row.warehouse_id)}}</td><td>{{row.order_id}}</td><td>{{row.remaining}}</td><td>{{new Date(row.expires_at).toLocaleString('ru')}}</td><td class="actionbar"><button v-if="writable && row.editable" class="btn slim" @click="editReservation(row)">Изменить</button><button v-if="writable" class="btn slim" @click="remove(row)">Снять</button></td></template>
          <template v-else><td>{{row.name || label(products,row.output_product_id)}}</td><td>{{row.sku ? row.sku+' · '+types[row.type]+' · '+row.unit : row.version ? 'Версия '+row.version+(row.is_active ? ' · действует' : '') : row.is_virtual ? 'Виртуальный' : 'Физический'}}</td>
            <td class="actionbar"><button v-if="tab==='recipes'" class="btn slim" @click="openRecipe(row)">Сколько можно выпустить</button><button v-if="writable" class="btn slim" @click="draft={...JSON.parse(JSON.stringify(row)),is_active:!!row.is_active,is_virtual:!!row.is_virtual,allow_negative:!!row.allow_negative}">Изменить</button><button v-if="writable" class="btn slim ghost" @click="remove(row)">Удалить</button></td></template>
        </tr></tbody>
      </table>
    </div>
    <div v-if="tab==='movements' && (movementPage || rows.length===pageLength)" class="actionbar stock-nav" aria-label="Страницы журнала">
      <button type="button" class="btn slim" :disabled="movementPage===0" @click="movementPage--;refresh()">Назад</button>
      <span>Страница {{movementPage+1}}</span>
      <button type="button" class="btn slim" :disabled="rows.length<pageLength" @click="movementPage++;refresh()">Дальше</button>
    </div>
    <p v-if="!rows.length" class="empty">Записей пока нет.</p>
    <details class="stock-nav" @toggle="archiveOpen=$event.target.open">
      <summary>Прежний складской журнал · справочно</summary>
      <p>Начальные остатки нового склада вводятся документом «Инвентаризация» после сверки количества и стоимости.</p>
      <InventoryLedger v-if="archiveOpen" readonly />
      <CrmDataTable v-if="archiveOpen && db.warehouse.length" coll="warehouse" :rows="db.warehouse" />
    </details>
  </section>
</template>

<style scoped>
.stock-nav { margin-block: 12px; }
.stock-form { margin-block: 12px; }
.stock-form fieldset, .stock-line { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,160px),1fr)); gap:10px; padding:8px 0; border:0; min-width:0; }
.stock-line { grid-column:1/-1; border-bottom:1px solid var(--border); align-items:end; }
.stock-form label { display:grid; gap:4px; min-width:0; }
.stock-form input, .stock-form select { min-width:0; padding:7px; border:1px solid var(--border); border-radius:8px; color:var(--ink); background:var(--bg); }
.stock-form .stock-check { display:flex; align-items:center; }
.table-wrap { overflow:auto; }
</style>
