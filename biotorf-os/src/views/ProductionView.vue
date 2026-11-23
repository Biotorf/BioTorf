<script setup>
import { computed, inject, onMounted, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import { inventoryLink } from '@/utils/inventoryLink';
import { statusOptions } from '@/data/crmFields';
import CrmDataTable from '@/components/CrmDataTable.vue';
import CrmRowModal from '@/components/CrmRowModal.vue';
import StatusPill from '@/components/ui/StatusPill.vue';

const db = useDbStore();
const trainingActive = inject('trainingActive', ref(false));
const { canEditCollection } = usePermissions();
const { day } = useFormatters();
const rowOpen = ref(null);
const receiptError = ref('');
onMounted(async () => {
  try {
    await db.syncLogistics({ uploadPending: !trainingActive.value });
  } catch {
    receiptError.value = 'Не удалось обновить данные приёмки сырья.';
  }
});
const statusFilter = ref('Все');
const source = computed(() => db.data.production || []);
const statuses = computed(() => ['Все', ...statusOptions('production', source.value)]);
const rows = computed(() => source.value.filter((row) => statusFilter.value === 'Все' || row.status === statusFilter.value));
function canPost(row) {
  return canEditCollection('production') && row.status === 'Завершено' && row.powderUsedKg > 0 &&
    !!row.inputLot && !!row.lot && ['Пройден', 'Отклонён'].includes(row.qcStatus);
}
</script>

<template>
  <section>
    <div class="pagehead">
      <div>
        <h1 data-tour="production-view">Производство</h1>
        <p class="subtitle">Планируйте выпуск по заказам и фиксируйте расход порошка и фактический выпуск.</p>
      </div>
      <button v-if="canEditCollection('production')" class="btn primary" data-tour="production-create" @click="rowOpen = { record: null }">Новая партия</button>
    </div>
    <p v-if="receiptError" class="danger-text" role="alert">{{ receiptError }}</p>
    <div class="toolbar">
      <label>Статус
        <select v-model="statusFilter" class="select"><option v-for="status in statuses" :key="status">{{ status }}</option></select>
      </label>
      <a href="#/shipments?kind=supply">Поставки порошка</a>
    </div>
    <div v-if="rows.length" class="batch-grid">
      <article v-for="row in rows" :key="row.id" class="panel batch">
        <header>
          <h2>{{ row.product || db.skuById(row.sku)?.name || row.id }}</h2>
          <StatusPill :status="row.status" />
        </header>
        <p class="subtitle">{{ [row.lot || row.batch, row.date ? day(row.date) : '', row.orderId ? 'Под заказ' : ''].filter(Boolean).join(' · ') }}</p>
        <p v-if="row.qty || row.plannedVolumeL"><strong>План</strong> {{ row.qty ?? '—' }} {{ row.unit || 'шт.' }} <span v-if="row.plannedVolumeL">· {{ row.plannedVolumeL }} л</span></p>
        <p v-if="row.plannedPowderKg != null"><strong>Порошок по рецептуре {{ row.recipeVersion }}</strong> {{ row.plannedPowderKg }} кг</p>
        <p v-if="row.actualQty != null"><strong>Выпуск</strong> {{ row.actualQty }} {{ row.unit || 'шт.' }} · {{ row.qcStatus || 'Контроль ожидается' }}</p>
        <div class="actionbar">
          <button v-if="canEditCollection('production')" class="btn slim" @click="rowOpen = { record: row }">{{ row.status === 'Завершено' ? 'Открыть партию' : 'Заполнить партию' }}</button>
          <a v-if="canPost(row)" :href="inventoryLink('production', 'production', row.id)">Провести на складе</a>
        </div>
      </article>
    </div>
    <p v-else class="empty">Партий по этому фильтру пока нет.</p>
    <details class="panel full-table">
      <summary>Таблица производства</summary>
      <CrmDataTable coll="production" :rows="rows" empty="Партий нет." />
    </details>
    <CrmRowModal v-if="rowOpen" coll="production" :record="rowOpen.record" @close="rowOpen = null" />
  </section>
</template>

<style scoped>
.batch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 250px), 1fr)); gap: 12px; }
.batch header { display: flex; align-items: start; justify-content: space-between; gap: 8px; }
.batch .actionbar { align-items: center; }
.full-table { margin-top: 16px; }
.full-table summary { cursor: pointer; font-weight: 650; }
.full-table .table-wrap { margin-top: 12px; }
</style>
