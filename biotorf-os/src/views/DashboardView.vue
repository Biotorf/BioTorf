<script setup>
import { computed } from 'vue';
import { useDbStore, isLate } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';

const db = useDbStore();
const ui = useUiStore();
const { day } = useFormatters();
const doneTask = new Set(['Выполнена', 'Отменена']);
const taskList = computed(() => db.tasks.filter((task) => !doneTask.has(task.status))
  .slice().sort((a, b) => (a.due || '9999').localeCompare(b.due || '9999')).slice(0, 6));
const unread = computed(() => db.comms.filter((item) => item.dir === 'in' && !item.read).length);
const productionPlans = computed(() => (db.data.production || []).filter(({ status }) => ['План', 'В работе'].includes(status)).length);
const unsettled = computed(() => db.invoices.filter((invoice) =>
  !['Отменён', 'Отменен'].includes(invoice.status) && db.invoiceBalance(invoice) > 0).length);
const shipments = computed(() => db.shipments.filter((record) => !record.received && !['Отменена', 'Получено клиентом'].includes(record.status)).length);
const sales = [
  ['comms', 'Входящие', unread, 'Открыть переписку и звонки'],
  ['crm', 'Клиенты', null, 'Найти карточку клиента'],
  ['journey', 'Продажи', null, 'Продолжить оформление сделки'],
];
const operations = [
  ['shipments', 'Поставки и отгрузки', shipments, 'Принять сырьё или оформить доставку'],
  ['production', 'Производство', productionPlans, 'Открыть планы и выпуск'],
  ['warehouse', 'Склад', null, 'Проверить остатки и движения'],
  ['finance', 'Финансы', unsettled, 'Сверить счета и оплаты'],
];
const operationsFirst = computed(() => ['production', 'warehouse', 'logistics', 'finance'].includes(ui.role));
const groups = computed(() => operationsFirst.value
  ? [['Операции', operations], ['Работа с клиентами', sales]]
  : [['Работа с клиентами', sales], ['Операции', operations]]);
</script>

<template>
  <section class="home">
    <header class="pagehead">
      <div>
        <h1>Главная</h1>
        <p class="subtitle">Входящие обращения, задачи и рабочие операции BioTorf.</p>
      </div>
      <a class="btn primary" href="#/crm">Открыть клиентов</a>
    </header>

    <section v-for="[title, entries] in groups" :key="title" class="work-group">
      <h2>{{ title }}</h2>
      <div class="work-grid">
        <button v-for="[view, label, count, description] in entries" :key="view" type="button" class="panel work-link" @click="ui.go(view)">
          <span class="work-title">{{ label }}<span v-if="count?.value > 0" class="pill">{{ count.value }}</span></span>
          <span class="subtitle">{{ description }}</span>
        </button>
      </div>
    </section>

    <section class="panel tasks">
      <header class="panel-head">
        <h2>Ближайшие задачи</h2>
        <a href="#/tasks">Все задачи</a>
      </header>
      <p v-if="!taskList.length" class="subtitle">Открытых задач пока нет.</p>
      <button v-for="task in taskList" :key="task.id" type="button" class="task-row" @click="ui.openRecord('task', task.id)">
        <span>
          <strong>{{ task.title }}</strong>
          <small>{{ [task.owner, task.due ? day(task.due) : 'Без срока'].filter(Boolean).join(' · ') }}</small>
        </span>
        <StatusPill :status="isLate(task.due) ? 'Просрочено' : task.status" />
      </button>
    </section>
  </section>
</template>

<style scoped>
.home { max-width: 1100px; }
.pagehead .btn { text-decoration: none; display: inline-block; }
.work-group { margin-bottom: 24px; }
.work-group h2 { margin-bottom: 9px; }
.work-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 210px), 1fr)); gap: 10px; }
.work-link { display: grid; gap: 5px; text-align: start; padding: 15px; align-content: start; }
.work-link:hover, .task-row:hover { background: #f7fbf8; border-color: #b3d2c4; }
.work-title { display: flex; align-items: center; gap: 6px; font-weight: 720; }
.tasks { max-width: 730px; }
.task-row { background: #fff; width: 100%; border: 0; border-bottom: 1px solid #edf2ef; text-align: start; }
.task-row small { display: block; color: var(--muted); }
</style>
