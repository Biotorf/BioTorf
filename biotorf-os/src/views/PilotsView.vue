<script setup>
import { statusOptions } from '@/data/crmFields';
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Агрономия» (руководство v0.9 §8): список пилотов, регистрации обработок и
// результатов; клик — карточка пилота (§5) + переход в связанный сквозной процесс.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import BackendBadge from '@/components/ui/BackendBadge.vue';

import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
const editor = ref(null);
function openEditor(record = null) { editor.value = { record }; }

const db = useDbStore();
const ui = useUiStore();

const STATUSES = computed(() => ['Все', ...statusOptions('pilots', db.pilots || [], db.data.pilotStages)]);
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

</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Агрономия · Пилоты</h1>
        <ManualLink />
        <div class="subtitle">Пилоты, обработки и агрономические результаты</div>
      <BackendBadge collection="pilots" />
      </div>
      <input :value="ui.search" @input="ui.search = $event.target.value" class="input" style="max-width:260px" placeholder="Поиск по пилотам…" />
    
      <button class="btn primary slim" @click="openEditor()" title="Добавить запись вручную">＋ Добавить</button>
    </div>

    <CrmRowModal
      v-if="editor"
      inline
      :key="editor.record?.id || 'new'"
      coll="pilots"
      :record="editor.record"
      @close="editor = null"
    />

    <div class="insight" style="margin-bottom:14px;gap:8px">
      <b>Статус:</b>
      <select v-model="statusFilter" class="select" style="max-width:200px"><option v-for="s in STATUSES" :key="s">{{ s }}</option></select>
    </div>

    <section class="panel">
      <CrmDataTable coll="pilots" :rows="pilots" empty="Пилотов нет.">
        <template #actions="{ row: p }">
          <button class="btn slim ghost" @click="ui.openRecord('pilot', p.id)">Открыть</button>
          <button v-if="p.journeyId" class="btn slim ghost" @click="ui.openJourney(p.journeyId)">Процесс</button>
          <button class="btn slim ghost" @click="openEditor(p)">Изменить</button>
        </template>
      </CrmDataTable>
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
