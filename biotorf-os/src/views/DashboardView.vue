<script setup>
import { computed, ref } from 'vue';
import { useDbStore, isLate } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import { usePermissions } from '@/composables/usePermissions';
import StatusPill from '@/components/ui/StatusPill.vue';

const db = useDbStore();
const ui = useUiStore();
const { day, money } = useFormatters();
const { canEditCollection, canSeeFarm } = usePermissions();
const scope = ref('all');
const normalize = (value) => String(value ?? '').trim().toLowerCase();
const myNames = computed(() => [ui.login, ui.name].map(normalize).filter(Boolean));
const belongsToMe = (record) => myNames.value.includes(normalize(record.owner));
const visibleFarm = (id) => !id || !db.farmById(id) || canSeeFarm(db.farmById(id));
const doneTask = new Set(['Выполнена', 'Отменена', 'Отменена автоматически']);
const stoppedSale = new Set(['Завершено', 'Отменён', 'Отказ']);
const canceledInvoice = new Set(['Отменён', 'Отменен']);
const dueOrder = (a, b) => String(a.due || a.next || '9999').localeCompare(String(b.due || b.next || '9999'));

const activeTasks = computed(() => db.tasks.filter((task) => !doneTask.has(task.status)));
const tasks = computed(() => activeTasks.value.filter((task) => scope.value === 'all' || belongsToMe(task))
  .sort(dueOrder).slice(0, 6));
const dueTasks = computed(() => activeTasks.value.filter(({ due }) => isLate(due)).length);
const activeSales = computed(() => db.journeys.filter((sale) => !stoppedSale.has(sale.stage) && visibleFarm(sale.farmId)));
const sales = computed(() => activeSales.value.slice().sort(dueOrder).slice(0, 5));
const invoices = computed(() => db.invoices.filter((invoice) => !canceledInvoice.has(invoice.status) && visibleFarm(invoice.farmId))
  .map((invoice) => db.invoiceBalance(invoice)).filter((balance) => balance > 0));
const plans = computed(() => (db.data.production || []).filter(({ status }) => ['План', 'В работе'].includes(status)).length);
const readyToShip = computed(() => db.shipments.filter((item) => !item.received && visibleFarm(item.farmId) &&
  !['Отменена', 'Получено клиентом'].includes(item.status)).length);

const metrics = computed(() => [
  { label: 'Активные продажи', value: activeSales.value.length, href: '#/journey', detail: 'Открыть маршруты', tone: 'mint' },
  { label: 'Открытые задачи', value: activeTasks.value.length, href: '#/tasks', detail: `Просрочено: ${dueTasks.value}`, tone: 'blue' },
  { label: 'К получению', value: money(invoices.value.reduce((a, b) => a + b, 0)), href: '#/finance', detail: `Счетов с остатком: ${invoices.value.length}`, tone: 'sand' },
  { label: 'Планы выпуска', value: plans.value, href: '#/production', detail: 'Запланировано или в работе', tone: 'lilac' },
]);

function clientName(sale) {
  return db.farmById(sale.farmId)?.name || db.leadById(sale.leadId)?.name || 'Обращение без названия';
}
</script>

<template>
  <section class="workspace">
    <header class="workspace-head">
      <div>
        <h1>Рабочий день</h1>
        <p class="subtitle">Задачи, продажи и операции BioTorf</p>
      </div>
      <div class="actionbar workspace-actions">
        <a class="btn" href="#/comms">Открыть входящие</a>
        <a v-if="canEditCollection('farms')" class="btn primary" href="#/crm?new=1">＋ Новый клиент</a>
      </div>
    </header>

    <div class="metrics" data-tour="workday-summary" aria-label="Показатели рабочего дня">
      <a v-for="metric in metrics" :key="metric.label" class="metric" :class="metric.tone" :href="metric.href">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <small>{{ metric.detail }}</small>
      </a>
    </div>

    <div class="workspace-grid">
      <section class="panel work-panel">
        <header class="section-head">
          <h2>Задачи</h2>
          <div v-if="myNames.length" class="segmented" aria-label="Чьи задачи">
            <button type="button" :aria-pressed="scope === 'all'" @click="scope = 'all'">Все</button>
            <button type="button" :aria-pressed="scope === 'mine'" @click="scope = 'mine'">Мои</button>
          </div>
        </header>
        <p v-if="!tasks.length" class="empty-list">Открытых задач пока нет.</p>
        <button v-for="task in tasks" :key="task.id" type="button" class="work-row" @click="ui.openRecord('task', task.id)">
          <span class="row-copy">
            <strong>{{ task.title }}</strong>
            <small>{{ [task.owner, task.due ? day(task.due) : 'Без срока'].filter(Boolean).join(' · ') }}</small>
          </span>
          <StatusPill :status="isLate(task.due) ? 'Просрочено' : task.status" />
        </button>
        <a class="panel-link" href="#/tasks">Все задачи →</a>
      </section>

      <section class="panel work-panel">
        <header class="section-head">
          <h2>Следующие продажи</h2>
          <a href="#/pipeline">Воронка</a>
        </header>
        <p v-if="!sales.length" class="empty-list">Активных продаж пока нет.</p>
        <a v-for="sale in sales" :key="sale.id" class="work-row" :href="'#/journey?id=' + encodeURIComponent(sale.id)">
          <span class="row-copy">
            <strong>{{ clientName(sale) }}</strong>
            <small>{{ [sale.owner, sale.next ? 'Контакт ' + day(sale.next) : 'Без даты контакта'].filter(Boolean).join(' · ') }}</small>
          </span>
          <StatusPill :status="sale.stage" />
        </a>
        <a class="panel-link" href="#/journey">Открыть продажи →</a>
      </section>
    </div>

    <section class="panel operations">
      <header class="section-head"><h2>Операции</h2></header>
      <div class="operation-links">
        <a href="#/shipments?kind=supply"><strong>Поставка порошка</strong><small>Документы закупки и приёмки</small></a>
        <a href="#/warehouse"><strong>Склад</strong><small>Партии, остатки и резервы</small></a>
        <a href="#/shipments?kind=dispatch"><strong>Отгрузки</strong><small>Открыто {{ readyToShip }}</small></a>
        <a href="#/automation"><strong>Автоматизация</strong><small>Правила и история выполнения</small></a>
      </div>
    </section>
  </section>
</template>

<style scoped>
.workspace { max-width: 1280px; margin-inline: auto; }
.workspace-head, .section-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.workspace-head {
  margin-bottom: 16px;
  padding: clamp(16px, 3vw, 26px);
  align-items: center;
  background: linear-gradient(118deg, #103d2e, #176747);
  border-radius: 17px;
  color: #fff;
  box-shadow: var(--shadow);
}
.workspace-head h1 { font-size: clamp(25px, 3vw, 34px); margin-bottom: 4px; color: inherit; }
.workspace-head p { margin: 0; color: #d8eee1; }
.workspace-actions .btn { border-color: #d8eee1; color: #164835; background: #f4fbf6; }
.workspace-actions .btn.primary { border-color: #aee0bf; color: #103e2a; background: #bceaca; box-shadow: none; }
.workspace-actions .btn.primary:hover { background: #d4f2dd; color: #103e2a; }
.workspace-head .btn:focus-visible { outline-color: #fff; }
.workspace-head a, .work-panel a { text-decoration: none; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.metric { display: grid; min-width: 0; gap: 3px; padding: 15px 17px; border: 1px solid #e2ebe5; border-radius: 14px; color: var(--ink); text-decoration: none; }
.metric:hover { border-color: #95b8a8; box-shadow: var(--shadow); }
.metric { border-top-width: 3px; }
.metric.mint { border-top-color: #63ac82; }
.metric.blue { border-top-color: #87a9ca; }
.metric.sand { border-top-color: #cab07b; }
.metric.lilac { border-top-color: #a69bbd; }
.metric > span { font-weight: 650; }
.metric > strong { overflow-wrap: anywhere; font-size: clamp(22px, 3vw, 29px); line-height: 1.25; letter-spacing: -.025em; font-variant-numeric: tabular-nums; }
.metric > small { color: #4e6660; }
.mint { background: #f2faf5; }
.blue { background: #f4f8fd; }
.sand { background: #fffaf0; }
.lilac { background: #f8f6fc; }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 1.13fr) minmax(0, 1fr); gap: 16px; }
.work-panel { min-width: 0; padding: 15px 17px 12px; }
.section-head { margin-bottom: 6px; min-height: 33px; }
.section-head > a, .panel-link { font-size: 13px; font-weight: 650; }
.segmented { display: inline-flex; gap: 2px; border: 1px solid #e4ebe5; background: #f4f7f4; border-radius: 10px; padding: 2px; }
.segmented button { border: 0; background: transparent; color: #48655a; padding: 4px 9px; border-radius: 8px; font-size: 12px; }
.segmented button[aria-pressed="true"] { color: #165f48; background: #fff; box-shadow: 0 1px 4px #cddbd4; font-weight: 700; }
.work-row { min-width: 0; width: 100%; min-height: 52px; border: 0; border-bottom: 1px solid #edf2ee; background: transparent; color: var(--ink); padding: 7px 0; display: flex; align-items: center; justify-content: space-between; gap: 10px; text-align: start; }
.work-row:hover { background: #f5faf7; }
.row-copy { min-width: 0; overflow-wrap: anywhere; }
.row-copy small { display: block; color: #546c63; }
.work-row .pill { white-space: normal; text-align: center; max-width: 42%; }
.panel-link { display: inline-block; margin-top: 10px; }
.empty-list { padding: 12px 0; color: #546c63; }
.operations { margin-top: 16px; padding: 14px 17px; }
.operation-links { display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: 8px; }
.operation-links a { border: 1px solid #e3ebe6; background: #fbfdfb; padding: 9px 11px; border-radius: 10px; text-decoration: none; }
.operation-links a:hover { background: #f1f8f3; }
.operation-links small { display: block; color: #546c63; }
@media(max-width: 960px) { .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media(max-width: 720px) { .workspace-grid { grid-template-columns: minmax(0, 1fr); } .operation-links { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
