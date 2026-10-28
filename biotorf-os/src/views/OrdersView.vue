<script setup>
// «Заказы» (§3 шаги 18–20): реестр заказов с переходом в карточку (§5).
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import CrmImportModal from '@/components/CrmImportModal.vue';
import CrmRowModal from '@/components/CrmRowModal.vue';

const rowModal = ref(null);

const importColl = ref('');   // непусто — открыта модалка импорта

const db = useDbStore();
const ui = useUiStore();
const { day, money, num } = useFormatters();
const statusFilter = ref('Все');
const STATUSES = computed(() => ['Все', ...new Set(db.orders.map((o) => o.status))]);
const rows = computed(() =>
  db.orders
    .filter((o) => statusFilter.value === 'Все' || o.status === statusFilter.value)
    .filter((o) => {
      const q = ui.search.toLowerCase();
      return !q || [o.id, o.farmName, db.farmById(o.farmId)?.name, o.sku, o.status].join(' ').toLowerCase().includes(q);
    })
    .slice().sort((a, b) => (a.date < b.date ? 1 : -1))
);
const farmName = (id) => db.farmById(id)?.name || '—';
const skuName = (id) => db.skuById(id)?.name || id;
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Заказы</h1>
        <div class="subtitle">Коммерческие заказы: позиции, суммы и статусы</div>
      </div>
      <BackendBadge collection="orders" />
    </div>

    <div class="toolbar">
      <input :value="ui.search" @input="ui.search = $event.target.value" class="input" style="max-width:320px" placeholder="Поиск по заказам…" />
      <select v-model="statusFilter" class="select" style="max-width:220px"><option v-for="s in STATUSES" :key="s">{{ s }}</option></select>
      <button class="btn slim" @click="importColl = 'orders'" title="Загрузить заказы из CSV/JSON">⇪ Импорт</button>
      <button class="btn primary slim" @click="rowModal = { coll: 'orders' }">＋ Заказ</button>
    </div>

    <section class="panel">
      <table class="table">
        <thead><tr><th>Заказ</th><th>Хозяйство</th><th>Продукт</th><th>Кол-во</th><th>Сумма</th><th>Дата</th><th>Статус</th><th></th></tr></thead>
        <tbody>
          <tr v-for="o in rows" :key="o.id" class="row-click" @click="ui.openRecord('order', o.id)">
            <td><b>{{ o.id }}</b><div class="mini" v-if="o.journeyId">Маршрут {{ o.journeyId }}</div></td>
            <td>{{ o.farmName || farmName(o.farmId) }}</td>
            <td>{{ o.product || skuName(o.sku) }}</td>
            <td>{{ num(o.qty) }} {{ o.unit || 'шт.' }}</td>
            <td class="mono">{{ money(o.amount) }}</td>
            <td>{{ day((o.date || '').slice(0, 10)) }}</td>
            <td><StatusPill :status="o.status" /></td>
            <td><button v-if="o.journeyId" class="btn slim" @click.stop="ui.openJourney(o.journeyId)">Процесс</button> <button class="btn slim ghost" @click.stop="rowModal = { coll: 'orders', record: o }">✎</button></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="8" class="empty">Заказов нет. Заказ создаётся из сквозного процесса после подтверждения КП (§3 шаг 19).</td></tr>
        </tbody>
      </table>
    </section>

    <CrmImportModal v-if="importColl" :coll="importColl" @close="importColl = ''" />
    <CrmRowModal v-if="rowModal" :coll="rowModal.coll" :record="rowModal.record" @close="rowModal = null" />
  </div>
</template>

<style scoped>
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
.mini { font-size: 12px; color: var(--muted, #7b8a86); }
.mono { font-variant-numeric: tabular-nums; }
</style>
