<script setup>
import { computed, ref } from 'vue';
import { checkApi } from '@/api/commsClient';
import { usePermissions } from '@/composables/usePermissions';
import CrmDataTable from '@/components/CrmDataTable.vue';
import InventoryLedger from '@/components/InventoryLedger.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
import { useDbStore } from '@/stores/db';

const db = useDbStore();
const { canEdit } = usePermissions();
const deleting = ref(null);
const deleteError = ref('');
const deleteNotice = ref('');
async function removeLegacy(row) {
  if (deleting.value || !canEdit('warehouse')) return;
  if (!confirm(`Удалить строку «${row.batch || row.lot || row.sku || row.id}» из прежнего реестра?`)) return;
  deleting.value = row.id;
  deleteError.value = '';
  deleteNotice.value = '';
  try {
    if (!(await checkApi({ force:true }))) throw new Error('Сервер недоступен. Обновите страницу и повторите удаление.');
    await db.deleteRow('warehouse', row.id);
    deleteNotice.value = 'Строка удалена из прежнего реестра.';
  } catch (error) {
    deleteError.value = error.message;
  } finally {
    deleting.value = null;
  }
}
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
        <div class="subtitle">Остатки пасты и готовой продукции по партиям</div>
      </div>
    </div>

    <p v-if="deleteError" class="note danger-text" role="alert">{{deleteError}}</p>
    <p v-if="deleteNotice" class="note" role="status">{{deleteNotice}}</p>
    <InventoryLedger @legacy-mode="legacyMode = $event">
      <template #legacy>
        <h2>Прежний складской реестр</h2>
        <p class="mini">Данные CRM и локальной копии доступны только для справки. Остатки складского журнала здесь не отображаются.</p>
        <CrmDataTable v-if="legacyRows.length" coll="warehouse" :rows="legacyRows">
          <template v-if="canEdit('warehouse')" #actions="{row}">
            <button type="button" class="btn slim ghost danger-text" :disabled="!!deleting" @click="removeLegacy(row)">
              {{deleting === row.id ? 'Удаляем…' : 'Удалить'}}
            </button>
          </template>
        </CrmDataTable>
        <p v-else class="empty">В прежнем реестре нет доступных записей.</p>
      </template>
    </InventoryLedger>

    <details v-if="!legacyMode && legacyRows.length" class="legacy-warehouse">
      <summary>Прежний складской реестр · справочно ({{ legacyRows.length }})</summary>
      <p class="mini">Эти строки не участвуют в остатках журнала. Для переноса сверьте партии и внесите начальные остатки.</p>
      <CrmDataTable coll="warehouse" :rows="legacyRows">
          <template v-if="canEdit('warehouse')" #actions="{row}">
            <button type="button" class="btn slim ghost danger-text" :disabled="!!deleting" @click="removeLegacy(row)">
              {{deleting === row.id ? 'Удаляем…' : 'Удалить'}}
            </button>
          </template>
        </CrmDataTable>
    </details>
  </div>
</template>

<style scoped>
.legacy-warehouse { margin-top: 20px; }
.legacy-warehouse summary { cursor: pointer; }
.legacy-warehouse p { margin: 8px 0; }
</style>
