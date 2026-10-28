<script setup>
// «Склад» (демо v0.9): остатки по SKU с резервами под заказы.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';

import CrmRowModal from '@/components/CrmRowModal.vue';
const rowColl = ref('warehouse');
const rowOpen = ref(false);

const db = useDbStore();
const { num } = useFormatters();
const query = ref('');
const rows = computed(() =>
  (db.warehouse || [])
    .map((w) => ({ ...w, skuName: db.skuById(w.sku)?.name || w.sku, free: (w.qty || 0) - (w.reserved || 0) }))
    .filter((w) => !query.value || [w.sku, w.skuName, w.warehouse].join(' ').toLowerCase().includes(query.value.toLowerCase()))
);
const totals = computed(() => ({
  qty: rows.value.reduce((s, w) => s + w.qty, 0),
  reserved: rows.value.reduce((s, w) => s + w.reserved, 0),
}));
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Склад</h1>
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
      <table class="table">
        <thead><tr><th>SKU</th><th>Продукт</th><th>Склад</th><th>Остаток</th><th>Резерв</th><th>Свободно</th></tr></thead>
        <tbody>
          <tr v-for="w in rows" :key="w.id">
            <td><b>{{ w.sku }}</b></td>
            <td>{{ w.skuName }}</td>
            <td>{{ w.warehouse }}</td>
            <td class="mono">{{ num(w.qty) }} {{ w.unit }}</td>
            <td class="mono">{{ num(w.reserved) }} {{ w.unit }}</td>
            <td class="mono"><span class="pill" :class="w.free <= 0 ? 'red' : ''">{{ num(w.free) }} {{ w.unit }}</span></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="6" class="empty">Остатков нет.</td></tr>
        </tbody>
      </table>
    </section>

    <div class="note" style="margin-top:12px">Автоматические складские проводки отключены (§3, ОГРАНИЧЕНИЕ v0.9): резервы — справочные.</div>
  </div>
  <CrmRowModal v-if="rowOpen" :coll="rowColl" @close="rowOpen = false" />
</template>

<style scoped>.mono { font-variant-numeric: tabular-nums; }</style>
