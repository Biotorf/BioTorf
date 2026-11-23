<script setup>
import { inventoryLink } from '@/utils/inventoryLink';
import { crmPhotoLink } from '@/utils/crmPhotoLink';
import { usePermissions } from '@/composables/usePermissions';
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Заказы» (§3 шаги 18–20): реестр заказов с переходом в карточку (§5).
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import CrmImportModal from '@/components/CrmImportModal.vue';
import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';

const rowModal = ref(null);

const importColl = ref('');   // непусто — открыта модалка импорта

const db = useDbStore();
const ui = useUiStore();
const { canEdit } = usePermissions();
const statusFilter = ref('Все');
const STATUSES = computed(() => ['Все', ...new Set(db.orders.map((o) => o.status))]);
const rows = computed(() =>
  db.orders
    .filter((o) => statusFilter.value === 'Все' || o.status === statusFilter.value)
    .filter((o) => {
      const q = ui.search.toLowerCase();
      return !q || [o.id, o.number, o.num, o.farmName, db.farmById(o.farmId)?.name, o.sku, o.status].join(' ').toLowerCase().includes(q);
    })
    .slice().sort((a, b) => (a.date < b.date ? 1 : -1))
);
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Заказы</h1>
        <ManualLink />
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

    <CrmRowModal
      v-if="rowModal"
      inline
      :key="rowModal.record?.id || 'new'"
      :coll="rowModal.coll"
      :record="rowModal.record"
      @close="rowModal = null"
    />

    <div class="note">Подтверждённый заказ создаёт план выпуска. Перед отгрузкой проверьте доступный остаток и оформите резерв на складе.</div>

    <section class="panel">
      <CrmDataTable coll="orders" :rows="rows" empty="Заказов нет.">
        <template #actions="{ row: o }">
          <a v-if="canEdit('warehouse')" class="btn slim ghost" :href="inventoryLink('reserve', 'orders', o.id, o.id)">Резерв</a>
          <button class="btn slim ghost" @click="ui.openRecord('order', o.id)">Открыть</button>
          <a class="btn slim ghost" :href="crmPhotoLink('orders', o.id)">Фото</a>
          <button v-if="o.journeyId" class="btn slim ghost" @click="ui.openJourney(o.journeyId)">Процесс</button>
          <button class="btn slim ghost" @click="rowModal = { coll: 'orders', record: o }">Изменить</button>
        </template>
      </CrmDataTable>
    </section>

    <CrmImportModal v-if="importColl" :coll="importColl" @close="importColl = ''" />
  </div>
</template>

<style scoped>
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
.mini { font-size: 12px; color: var(--muted, #7b8a86); }
.mono { font-variant-numeric: tabular-nums; }
</style>
