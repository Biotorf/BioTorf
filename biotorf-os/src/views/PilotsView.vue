<script setup>
// «Агрономия» (руководство v0.9 §8): список пилотов, регистрации обработок и
// результатов; клик — карточка пилота (§5) + переход в связанный сквозной процесс.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';

const db = useDbStore();
const ui = useUiStore();
const { day, num } = useFormatters();

const STATUSES = ['Все', 'Запланирован', 'Идёт', 'Контроль', 'Завершен', 'Пилот прекращен'];
const statusFilter = ref('Все');

const pilots = computed(() =>
  db.pilots
    .filter((p) => statusFilter.value === 'Все' || p.status === statusFilter.value)
    .filter((p) => {
      const q = ui.search.toLowerCase();
      if (!q) return true;
      return [p.title, p.crop, p.farmName, p.owner, p.status].join(' ').toLowerCase().includes(q);
    })
);

const appsOf = (pid) => (db.data.applications || []).filter((a) => a.pilotId === pid);
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Агрономия · Пилоты</h1>
        <div class="subtitle">Пилоты, обработки и агрономические результаты</div>
      </div>
      <input :value="ui.search" @input="ui.search = $event.target.value" class="input" style="max-width:260px" placeholder="Поиск по пилотам…" />
    </div>

    <div class="insight" style="margin-bottom:14px;gap:8px">
      <b>Статус:</b>
      <select v-model="statusFilter" class="select" style="max-width:200px"><option v-for="s in STATUSES" :key="s">{{ s }}</option></select>
    </div>

    <section class="panel">
      <table class="table">
        <thead><tr><th>Пилот</th><th>Культура</th><th>Площадь, га</th><th>Ответственный</th><th>След. контроль</th><th>Обработок</th><th>Статус</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in pilots" :key="p.id" class="row-click" @click="ui.openRecord('pilot', p.id)">
            <td><b>{{ p.title || p.id }}</b><div class="mini">{{ p.farmName || '' }}</div></td>
            <td>{{ p.crop || '—' }}</td>
            <td>{{ num(p.area) }}</td>
            <td>{{ p.owner || '—' }}</td>
            <td>{{ day(p.nextCheck || p.next) }}</td>
            <td>{{ appsOf(p.id).length }}</td>
            <td><StatusPill :status="p.status" /></td>
            <td><button v-if="p.journeyId" class="btn slim" @click.stop="ui.openJourney(p.journeyId)">Процесс</button></td>
          </tr>
          <tr v-if="!pilots.length"><td colspan="8" class="empty">Пилотов нет. Пилот создаётся из сквозного процесса для агропроизводителя (§3 шаг 5).</td></tr>
        </tbody>
      </table>
    </section>

    <div class="note" style="margin-top:12px">
      Обработки фиксируются отдельными записями в карточке пилота; проверенные схемы применения — в «Базе знаний».
    </div>
  </div>
</template>

<style scoped>
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
</style>
