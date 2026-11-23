<script setup>
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import CrmDataTable from '@/components/CrmDataTable.vue';
import CrmRowModal from '@/components/CrmRowModal.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const ui = useUiStore();
const { canEditCollection } = usePermissions();
const { money } = useFormatters();
const editor = ref(null);
const mode = ref('invoices');
const filter = ref('all');
const query = ref('');
const cancellations = new Set(['Отменён', 'Отменен']);
const invoices = computed(() => db.invoices.slice().sort((a, b) => String(a.due || '9999').localeCompare(String(b.due || '9999'))));
const payments = computed(() => (db.data.payments || []).slice().sort((a, b) => String(b.date || '').localeCompare(String(a.date || ''))));
const totals = computed(() => {
  const active = invoices.value.filter((invoice) => !cancellations.has(invoice.status));
  const issued = active.reduce((sum, invoice) => sum + (Number(invoice.amount) || 0), 0);
  const balances = active.map(db.invoiceBalance);
  const debt = balances.reduce((sum, balance) => sum + balance, 0);
  return { issued, paid: issued - debt, debt, open: balances.filter((balance) => balance > 0).length };
});
const includesQuery = (values) => values.join(' ').toLowerCase().includes(query.value.trim().toLowerCase());
const visibleInvoices = computed(() => invoices.value.filter((invoice) => {
  const balance = db.invoiceBalance(invoice);
  const canceled = cancellations.has(invoice.status);
  return (filter.value === 'all' ||
    (filter.value === 'open' && !canceled && balance > 0) ||
    (filter.value === 'settled' && !canceled && balance <= 0)) &&
    includesQuery([invoice.number, invoice.id, invoice.status, invoice.orderId, db.farmById(invoice.farmId)?.name]);
}));
const visiblePayments = computed(() => payments.value.filter((payment) => {
  const invoice = db.invoiceById(payment.invoiceId);
  return includesQuery([payment.id, payment.method, payment.invoiceId, invoice?.number, invoice?.farmId && db.farmById(invoice.farmId)?.name]);
}));
function switchMode(value) {
  mode.value = value;
  query.value = '';
}
function openEditor(coll, record = null, initialValues = {}) {
  editor.value = { coll, record, initialValues };
}
function addPayment(invoice) {
  openEditor('payments', null, {
    invoiceId: invoice.id, orderId: invoice.orderId, amount: db.invoiceBalance(invoice),
    date: new Date().toISOString().slice(0, 10),
  });
}
</script>

<template>
  <section>
    <header class="pagehead">
      <div>
        <h1>Финансы</h1>
        <BackendBadge collection="invoices" />
      </div>
      <button v-if="canEditCollection(mode)" type="button" class="btn primary" @click="openEditor(mode)">
        {{ mode === 'invoices' ? '＋ Счёт' : '＋ Платёж' }}
      </button>
    </header>

    <div class="stats finance-stats" aria-label="Сводка по счетам">
      <div class="stat"><div class="label">Выставлено</div><div class="val">{{ money(totals.issued) }}</div></div>
      <div class="stat"><div class="label">Учтено в оплате</div><div class="val green">{{ money(totals.paid) }}</div></div>
      <div class="stat"><div class="label">К получению</div><div class="val">{{ money(totals.debt) }}</div></div>
      <div class="stat"><div class="label">Счетов с остатком</div><div class="val">{{ totals.open }}</div></div>
    </div>

    <div class="toolbar finance-tools" data-tour="finance-controls">
      <div class="actionbar" aria-label="Раздел финансов">
        <button class="btn slim" :class="{ primary: mode === 'invoices' }" :aria-pressed="mode === 'invoices'" @click="switchMode('invoices')">Счета</button>
        <button class="btn slim" :class="{ primary: mode === 'payments' }" :aria-pressed="mode === 'payments'" @click="switchMode('payments')">Платежи</button>
      </div>
      <input v-model="query" class="input" type="search" aria-label="Поиск в финансах" placeholder="Номер счёта или клиент" />
      <select v-if="mode === 'invoices'" v-model="filter" class="select" aria-label="Фильтр счетов">
        <option value="all">Все счета</option>
        <option value="open">С остатком</option>
        <option value="settled">Закрытые по сумме</option>
      </select>
    </div>

    <CrmDataTable v-if="mode === 'invoices'" coll="invoices" :rows="visibleInvoices" empty="Счета не найдены.">
      <template #actions="{ row }">
        <button class="btn slim ghost" @click="ui.openRecord('invoice', row.id)">Открыть</button>
        <button v-if="row.journeyId" class="btn slim ghost" @click="ui.openJourney(row.journeyId)">Продажа</button>
        <button v-if="canEditCollection('payments') && db.invoiceBalance(row) > 0 && !cancellations.has(row.status)"
                class="btn slim" @click="addPayment(row)">Внести платёж</button>
        <button v-if="canEditCollection('invoices')" class="btn slim ghost" @click="openEditor('invoices', row)">Изменить</button>
      </template>
    </CrmDataTable>
    <CrmDataTable v-else coll="payments" :rows="visiblePayments" empty="Платежи не найдены.">
      <template #actions="{ row }">
        <button v-if="row.invoiceId" type="button" class="btn slim ghost" @click="ui.openRecord('invoice', row.invoiceId)">Счёт</button>
        <button v-if="canEditCollection('payments')" type="button" class="btn slim ghost" @click="openEditor('payments', row)">Изменить</button>
      </template>
    </CrmDataTable>

    <CrmRowModal v-if="editor" :coll="editor.coll" :record="editor.record" :initial-values="editor.initialValues" @close="editor = null" />
  </section>
</template>

<style scoped>
.finance-tools { justify-content: flex-start; }
.finance-tools .select { width: min(200px, 100%); }
@media(max-width: 750px) { .finance-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
