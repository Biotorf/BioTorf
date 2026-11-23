<script setup>
import { computed, ref } from 'vue';
import CrmDataTable from '@/components/CrmDataTable.vue';
import InventoryLedger from '@/components/InventoryLedger.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
import { useDbStore } from '@/stores/db';

const db = useDbStore();
const legacyMode = ref(false);
const legacyRows = computed(() => (Array.isArray(db.warehouse) ? db.warehouse : [])
  .filter((row) => row && typeof row === 'object' && row.id));
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

    <InventoryLedger @legacy-mode="legacyMode = $event">
      <template #legacy>
        <h2>Прежний складской реестр</h2>
        <p class="mini">Данные CRM и локальной копии доступны только для справки. Остатки складского журнала здесь не отображаются.</p>
        <CrmDataTable v-if="legacyRows.length" coll="warehouse" :rows="legacyRows" />
        <p v-else class="empty">В прежнем реестре нет доступных записей.</p>
      </template>
    </InventoryLedger>

    <details v-if="!legacyMode && legacyRows.length" class="legacy-warehouse">
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
