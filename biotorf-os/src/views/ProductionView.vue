<script setup>
// «Производство» (демо v0.9): планы и партии розлива AGRO/HOME.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const { day, num } = useFormatters();
const statusFilter = ref('Все');
const rows = computed(() => (db.data.production || []).filter((p) => statusFilter.value === 'Все' || p.status === statusFilter.value));
const skuName = (id) => db.skuById(id)?.name || id;
const STATUSES = ['Все', 'План', 'В работе', 'Завершено'];
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Производство</h1>
        <div class="subtitle">Планы розлива и производственные партии (демонстрационный учёт)</div>
      </div>
      <BackendBadge collection="production" />
    </div>

    <div class="note">⚠️ Демонстрационный модуль: статусы не списывают сырьё и не резервируют склад автоматически.</div>

    <div class="toolbar">
      <select v-model="statusFilter" class="select" style="max-width:220px"><option v-for="s in STATUSES" :key="s">{{ s }}</option></select>
    </div>

    <section class="panel">
      <table class="table">
        <thead><tr><th>Партия</th><th>Продукт</th><th>Объем, шт</th><th>Дата плана</th><th>Номер лота</th><th>Статус</th></tr></thead>
        <tbody>
          <tr v-for="p in rows" :key="p.id">
            <td><b>{{ p.id }}</b></td>
            <td>{{ skuName(p.sku) }}</td>
            <td>{{ num(p.qty) }}</td>
            <td>{{ day((p.date || '').slice(0, 10)) }}</td>
            <td class="mono">{{ p.lot }}</td>
            <td><StatusPill :status="p.status" /></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="6" class="empty">Партий нет.</td></tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>.mono { font-variant-numeric: tabular-nums; }</style>
