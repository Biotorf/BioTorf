<script setup>
import { computed } from 'vue';
import CrmDataTable from '@/components/CrmDataTable.vue';
import InventoryLedger from '@/components/InventoryLedger.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
import { useDbStore } from '@/stores/db';

const db = useDbStore();
const legacyRows = computed(() => db.warehouse || []);
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Склад</h1>
        <ManualLink />
        <div class="subtitle">Остатки порошка и готовой продукции по партиям</div>
      </div>
    </div>

    <InventoryLedger />

    <details v-if="legacyRows.length" class="legacy-warehouse">
      <summary>Прежний складской реестр · справочно ({{ legacyRows.length }})</summary>
      <p class="mini">Эти строки не участвуют в остатках журнала. Для переноса сверьте партии и внесите начальные остатки.</p>
      <CrmDataTable coll="warehouse" :rows="legacyRows" />
    </details>
  </div>
</template>

<style scoped>
.legacy-warehouse { margin-top: 20px; }
.legacy-warehouse summary { cursor: pointer; }
.legacy-warehouse p { margin: 8px 0; }
</style>
