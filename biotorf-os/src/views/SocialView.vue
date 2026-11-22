<script setup>
import { statusOptions } from '@/data/crmFields';
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Маркетинг и соцсети» (демо v0.9 §8): контент-план публикаций, привязка к пилотам,
// согласование. Прямые публикации в Instagram в v0.9 не выполняются.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import BackendBadge from '@/components/ui/BackendBadge.vue';

import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
const rowColl = ref('social');
const rowOpen = ref(false);
const editRec = ref(null);
function openEdit(rec) { editRec.value = rec; rowOpen.value = true; }

const db = useDbStore();
const ui = useUiStore();
const statusFilter = ref('Все');
const rows = computed(() =>
  (db.social || [])
    .filter((s) => statusFilter.value === 'Все' || s.status === statusFilter.value)
    .slice().sort((a, b) => String(a.scheduledDate ?? a.date ?? '').localeCompare(String(b.scheduledDate ?? b.date ?? '')))
);
const STATUSES = computed(() => ['Все', ...statusOptions('social', db.social || [])]);
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Маркетинг и соцсети</h1>
        <ManualLink />
        <div class="subtitle">Контент-план публикаций, связь с пилотами и согласование</div>
      </div>
      <BackendBadge collection="social" />
    
      <button class="btn primary slim" @click="rowOpen = true" title="Добавить запись вручную">＋ Добавить</button>
    </div>

    <div class="note">В v0.9 публикации в Instagram автоматически не отправляются; результаты пилотов публикуются только после проверки агрономом и согласия хозяйства.</div>

    <div class="toolbar">
      <select v-model="statusFilter" class="select" style="max-width:240px"><option v-for="s in STATUSES" :key="s">{{ s }}</option></select>
    </div>

    <CrmDataTable coll="social" :rows="rows" empty="Публикаций нет.">
        <template #actions="{ row: s }">
          <button v-if="s.pilotId && s.pilotId !== 'Без привязки'" class="btn slim ghost" @click="ui.openRecord('pilot', s.pilotId)">Открыть пилот</button>
          <button class="btn slim ghost" @click="openEdit(s)">Изменить</button>
        </template>
      </CrmDataTable>
  </div>
  <CrmRowModal v-if="rowOpen" :coll="rowColl" :record="editRec" @close="rowOpen = false; editRec = null" />
</template>
