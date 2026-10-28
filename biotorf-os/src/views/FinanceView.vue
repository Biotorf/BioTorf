<script setup>
// «Финансы» (демо v0.9): счета, оплаты и дебиторка. Подтверждение оплаты — ручное (§3).
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';

import CrmRowModal from '@/components/CrmRowModal.vue';
const rowColl = ref('invoices');
const rowOpen = ref(false);

const db = useDbStore();
const ui = useUiStore();
const { day, money } = useFormatters();
const invoices = computed(() => db.invoices.slice().sort((a, b) => ((a.due || '') < (b.due || '') ? 1 : -1)));
const totals = computed(() => {
  const issued = invoices.value.reduce((s, i) => s + (Number(i.amount) || 0), 0);
  const paid = invoices.value.filter((i) => i.paid || i.status === 'Оплачен').reduce((s, i) => s + (Number(i.amount) || 0), 0);
  return { issued, paid, debt: issued - paid };
});
const isLate = (d) => d && new Date(d + 'T23:59:59') < new Date();
const orderFarm = (orderId) => {
  const o = db.orderById(orderId);
  return o ? db.farmById(o.farmId)?.name || o.farmName || o.farmId : '—';
};
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Финансы</h1>
        <div class="subtitle">Счета, оплаты и дебиторская задолженность</div>
      </div>
      <BackendBadge collection="invoices" />
    
      <button class="btn primary slim" @click="rowOpen = true" title="Добавить запись вручную">＋ Добавить</button>
    </div>

    <div class="stats">
      <div class="stat"><div class="label">Выставлено</div><div class="val">{{ money(totals.issued) }}</div><div class="foot">{{ invoices.length }} счетов</div></div>
      <div class="stat"><div class="label">Получено</div><div class="val green">{{ money(totals.paid) }}</div><div class="foot"><span class="tag">подтверждено вручную</span></div></div>
      <div class="stat"><div class="label">Дебиторка</div><div class="val" :class="totals.debt ? 'danger-text' : ''">{{ money(totals.debt) }}</div></div>
      <div class="stat"><div class="label">Неоплаченных счетов</div><div class="val">{{ invoices.filter(i => !i.paid && i.status !== 'Оплачен').length }}</div></div>
    </div>

    <div class="note">⚠️ ОГРАНИЧЕНИЕ v0.9: подтверждение оплаты ручное, без связи с банком; статусы не создают бухгалтерских проводок.</div>

    <section class="panel">
      <table class="table">
        <thead><tr><th>Счёт</th><th>Заказ / клиент</th><th>Сумма</th><th>Срок оплаты</th><th>Статус</th><th></th></tr></thead>
        <tbody>
          <tr v-for="i in invoices" :key="i.id" class="row-click" @click="ui.openRecord('invoice', i.id)">
            <td><b>{{ i.number || i.id }}</b></td>
            <td>{{ i.orderId || '—' }}<div class="mini">{{ orderFarm(i.orderId) }}</div></td>
            <td class="mono">{{ money(i.amount) }}</td>
            <td :class="!i.paid && isLate(i.due) ? 'danger-text' : ''">{{ day((i.due || '').slice(0, 10)) }}</td>
            <td><StatusPill :status="i.paid ? 'Оплачен' : i.status" /></td>
            <td><button v-if="i.journeyId" class="btn slim" @click.stop="ui.openJourney(i.journeyId)">Процесс</button></td>
          </tr>
          <tr v-if="!invoices.length"><td colspan="6" class="empty">Счетов нет. Счёт создаётся при подтверждении заказа в сквозном процессе (§3 шаг 19).</td></tr>
        </tbody>
      </table>
    </section>
  </div>
  <CrmRowModal v-if="rowOpen" :coll="rowColl" @close="rowOpen = false" />
</template>

<style scoped>
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
.mini { font-size: 12px; color: var(--muted, #7b8a86); }
.mono { font-variant-numeric: tabular-nums; }
</style>
