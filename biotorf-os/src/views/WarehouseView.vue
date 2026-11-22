<script setup>
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Склад» (демо v0.9): остатки по SKU с резервами под заказы.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';

import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
const rowColl = ref('warehouse');
const rowOpen = ref(false);
const editRec = ref(null);
function openEdit(rec) { editRec.value = rec; rowOpen.value = true; }

const db = useDbStore();
const { num } = useFormatters();
const query = ref('');
const rows = computed(() =>
  (db.warehouse || [])
    .filter((w) => !query.value || [w.sku, db.skuById(w.sku)?.name, w.warehouse ?? w.location]
      .join(' ').toLowerCase().includes(query.value.toLowerCase()))
);
const totals = computed(() => rows.value.reduce((sum, row) => {
  const legacyReserve = row.orderId && row.status === 'Зарезервировано' && row.reserved == null;
  sum.qty += legacyReserve ? 0 : Number(row.qty) || 0;
  sum.reserved += Number(legacyReserve ? row.qty : row.reserved) || 0;
  return sum;
}, { qty: 0, reserved: 0 }));
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Склад</h1>
        <ManualLink />
        <div class="subtitle">Остатки продукции и резервы под заказы</div>
      </div>
      <BackendBadge collection="warehouse" />
    
      <button class="btn primary slim" @click="rowOpen = true" title="Добавить запись вручную">＋ Добавить</button>
    </div>

    <div class="stats">
      <div class="stat"><div class="label">Позиций на складе</div><div class="val">{{ rows.length }}</div></div>
      <div class="stat"><div class="label">Всего, шт</div><div class="val">{{ num(totals.qty) }}</div></div>
      <div class="stat"><div class="label">В резерве, шт</div><div class="val">{{ num(totals.reserved) }}</div><div class="foot">под подтверждёнными заказами</div></div>
      <div class="stat"><div class="label">Свободно, шт</div><div class="val">{{ num(totals.qty - totals.reserved) }}</div></div>
    </div>

    <div class="toolbar">
      <input v-model="query" class="input" style="max-width:320px" placeholder="Поиск по SKU или складу…" />
    </div>

    <section class="panel">
      <CrmDataTable coll="warehouse" :rows="rows" empty="Остатков нет.">
        <template #actions="{ row: w }">
          <button class="btn slim ghost" @click="openEdit(w)">Изменить</button>
        </template>
      </CrmDataTable>
    </section>

    <div class="note" style="margin-top:12px">Автоматические складские проводки отключены (§3, ОГРАНИЧЕНИЕ v0.9): резервы — справочные.</div>
  </div>
  <CrmRowModal v-if="rowOpen" :coll="rowColl" :record="editRec" @close="rowOpen = false; editRec = null" />
</template>

<style scoped>.mono { font-variant-numeric: tabular-nums; }</style>
