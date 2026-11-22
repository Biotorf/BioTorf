<script setup>
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Финансы» (демо v0.9): счета, оплаты и дебиторка. Подтверждение оплаты — ручное (§3).
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';

import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
const rowColl = ref('invoices');
const rowOpen = ref(false);
const editRec = ref(null);
function openEdit(rec) { editRec.value = rec; rowOpen.value = true; }

const db = useDbStore();
const ui = useUiStore();
const { money } = useFormatters();
const invoices = computed(() => db.invoices.slice().sort((a, b) => ((a.due || '') < (b.due || '') ? 1 : -1)));
const totals = computed(() => {
  const active = invoices.value.filter((invoice) => !['Отменён', 'Отменен'].includes(invoice.status));
  const issued = active.reduce((s, i) => s + (Number(i.amount) || 0), 0);
  const balances = active.map(db.invoiceBalance);
  const debt = balances.reduce((sum, balance) => sum + balance, 0);
  return { issued, paid: issued - debt, debt, open: balances.filter((balance) => balance > 0).length };
});
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Финансы</h1>
        <ManualLink />
        <div class="subtitle">Счета, оплаты и дебиторская задолженность</div>
      </div>
      <BackendBadge collection="invoices" />
    
      <button class="btn primary slim" @click="rowOpen = true" title="Добавить запись вручную">＋ Добавить</button>
    </div>

    <div class="stats">
      <div class="stat"><div class="label">Выставлено</div><div class="val">{{ money(totals.issued) }}</div><div class="foot">{{ invoices.length }} счетов</div></div>
      <div class="stat"><div class="label">Получено</div><div class="val green">{{ money(totals.paid) }}</div><div class="foot"><span class="tag">подтверждено вручную</span></div></div>
      <div class="stat"><div class="label">Дебиторка</div><div class="val" :class="totals.debt ? 'danger-text' : ''">{{ money(totals.debt) }}</div></div>
      <div class="stat"><div class="label">Неоплаченных счетов</div><div class="val">{{ totals.open }}</div></div>
    </div>

    <div class="note">Дебиторка учитывает зарегистрированные платежи. Подтверждение оплаты сверяйте с поступлением денег. Синхронизация с банком и бухгалтерией не подключена.</div>

    <section class="panel">
      <CrmDataTable coll="invoices" :rows="invoices" empty="Счетов нет.">
        <template #actions="{ row: i }">
          <button class="btn slim ghost" @click="ui.openRecord('invoice', i.id)">Открыть</button>
          <button v-if="i.journeyId" class="btn slim ghost" @click="ui.openJourney(i.journeyId)">Процесс</button>
          <button class="btn slim ghost" @click="openEdit(i)">Изменить</button>
        </template>
      </CrmDataTable>
    </section>
  </div>
  <CrmRowModal v-if="rowOpen" :coll="rowColl" :record="editRec" @close="rowOpen = false; editRec = null" />
</template>

<style scoped>
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
.mini { font-size: 12px; color: var(--muted, #7b8a86); }
.mono { font-variant-numeric: tabular-nums; }
</style>
