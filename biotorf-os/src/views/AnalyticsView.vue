<script setup>
// «Аналитика» (демо v0.9): сводка по воронке, пилотам, заказам и финансам + источники лидов.
import { computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const { money, num } = useFormatters();

const dealSum = computed(() => db.deals.reduce((s, d) => s + (Number(d.amount) || 0), 0));
const weighted = computed(() => db.deals.reduce((s, d) => s + (Number(d.amount) || 0) * ((d.prob || 0) / 100), 0));
const liters = computed(() => db.deals.reduce((s, d) => s + (Number(d.liters) || 0), 0));
const activePilots = computed(() => db.pilots.filter((p) => !['Завершен', 'Пилот прекращен'].includes(p.status)).length);
const farmArea = computed(() => db.farms.reduce((s, f) => s + (Number(f.area) || 0), 0));
const invPaid = computed(() => db.invoices.filter((i) => i.paid || i.status === 'Оплачен').reduce((s, i) => s + (Number(i.amount) || 0), 0));
const invDebt = computed(() => db.invoices.filter((i) => !i.paid && i.status !== 'Оплачен').reduce((s, i) => s + (Number(i.amount) || 0), 0));

const sources = computed(() => {
  const map = {};
  for (const l of db.leads) map[l.source] = (map[l.source] || 0) + 1;
  for (const f of db.farms) map[f.source] = (map[f.source] || 0) + 1;
  const max = Math.max(1, ...Object.values(map));
  return Object.entries(map).map(([name, n]) => ({ name, n, pct: Math.round((n / max) * 100) }));
});

const funnel = computed(() => {
  const stages = ['Квалификация', 'Пилот согласован', 'КП отправлено', 'Счет/договор', 'Переговоры'];
  return stages.map((st) => ({ st, n: db.deals.filter((d) => d.stage === st).length }));
});
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Аналитика</h1>
        <div class="subtitle">Сводные показатели продаж, агрономии и финансов</div>
      </div>
      <BackendBadge />
    </div>

    <div class="stats">
      <div class="stat"><div class="label">Активных сделок</div><div class="val">{{ db.deals.length }}</div><div class="foot">{{ money(dealSum) }} потенциально</div></div>
      <div class="stat"><div class="label">Взвешенный прогноз</div><div class="val">{{ money(weighted) }}</div><div class="foot">сумма × вероятность закрытия</div></div>
      <div class="stat"><div class="label">Объем в сделках</div><div class="val">{{ num(liters) }} л</div><div class="foot">BIOTORF по активным сделкам</div></div>
      <div class="stat"><div class="label">Активных пилотов</div><div class="val">{{ activePilots }}</div><div class="foot">{{ num(farmArea) }} га под наблюдением хозяйств</div></div>
    </div>

    <div class="dash-grid">
      <section class="panel">
        <div class="panel-head"><div class="panel-title">Источники лидов и хозяйств</div><span class="mini">сколько приведено из каждого канала</span></div>
        <div v-for="s in sources" :key="s.name" class="bar-line">
          <div class="name">{{ s.name }}</div>
          <div class="track"><span :style="{ width: s.pct + '%' }"></span></div>
          <div class="val">{{ s.n }}</div>
        </div>
        <div class="mini" style="margin-top:14px">Маркетинг-атрибуция по продажам появится при привязке к бэкенду.</div>
      </section>

      <section class="panel">
        <div class="panel-head"><div class="panel-title">Финансовый статус</div></div>
        <div class="insight"><span>Оплачено по счетам</span><b class="green">{{ money(invPaid) }}</b></div>
        <div class="insight"><span>Дебиторская задолженность</span><b :class="invDebt ? 'danger-text' : ''">{{ money(invDebt) }}</b></div>
        <div class="insight"><span>Заказов всего</span><b>{{ db.orders.length }}</b></div>
        <div class="insight"><span>Хозяйств в базе</span><b>{{ db.farms.length }}</b></div>
        <div class="insight"><span>Лидов в работе</span><b>{{ db.leads.length }}</b></div>
      </section>
    </div>

    <section class="panel" style="margin-top:16px">
      <div class="panel-head"><div class="panel-title">Концентрация сделок по стадиям</div></div>
      <div class="chips">
        <span v-for="f in funnel" :key="f.st" class="chip neutral">{{ f.st }}: {{ f.n }}</span>
      </div>
      <div class="mini" style="margin-top:12px">Полная воронка — в разделе «Сделки и воронка»; сквозной маршрут — в «Сквозном процессе».</div>
    </section>
  </div>
</template>

<style scoped>.mini { font-size: 12px; color: var(--muted, #7b8a86); }</style>
