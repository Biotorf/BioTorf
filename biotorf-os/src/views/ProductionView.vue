<script setup>
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Производство» (демо v0.9): планы и партии розлива AGRO/HOME.
import { computed, onMounted, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import BackendBadge from '@/components/ui/BackendBadge.vue';

import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
const rowColl = ref('production');
const rowOpen = ref(false);
const editRec = ref(null);
function openEdit(rec) { editRec.value = rec; rowOpen.value = true; }

const db = useDbStore();
const receiptError = ref('');
onMounted(async () => {
  try {
    await db.syncLogistics();
  } catch {
    receiptError.value = 'Не удалось обновить данные приёмки сырья.';
  }
});
const statusFilter = ref('Все');
const rows = computed(() => (db.data.production || []).filter((p) => statusFilter.value === 'Все' || p.status === statusFilter.value));
const STATUSES = ['Все', 'План', 'В работе', 'Завершено'];
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Производство</h1>
        <ManualLink />
        <div class="subtitle">Планы розлива и производственные партии</div>
      </div>
      <BackendBadge collection="production" />
    
      <button class="btn primary slim" @click="rowOpen = true" title="Добавить запись вручную">＋ Добавить</button>
    </div>

    <div class="note">Из подтверждённого заказа поступает план по каждому артикулу. Перед запуском сверяйте остаток готового товара и принятые партии пасты в <a href="#/shipments">логистике</a>. Укажите партию сырья, фактический выпуск и результат контроля качества.</div>
    <p v-if="receiptError" class="danger-text" role="alert">{{ receiptError }}</p>

    <div class="toolbar">
      <select v-model="statusFilter" class="select" style="max-width:220px"><option v-for="s in STATUSES" :key="s">{{ s }}</option></select>
    </div>

    <section class="panel">
      <CrmDataTable coll="production" :rows="rows" empty="Партий нет.">
        <template #actions="{ row: p }">
          <button class="btn slim ghost" @click="openEdit(p)">Изменить</button>
        </template>
      </CrmDataTable>
    </section>
  </div>
  <CrmRowModal v-if="rowOpen" :coll="rowColl" :record="editRec" @close="rowOpen = false; editRec = null" />
</template>

<style scoped>.mono { font-variant-numeric: tabular-nums; }</style>
