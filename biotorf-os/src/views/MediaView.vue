<script setup>
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Медиатека» (демо v0.9 §8): фото/видео ДО-ПОСЛЕ по пилотам и кейсам.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import BackendBadge from '@/components/ui/BackendBadge.vue';

import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
const rowColl = ref('media');
const rowOpen = ref(false);
const editRec = ref(null);
function openEdit(rec) { editRec.value = rec; rowOpen.value = true; }

const db = useDbStore();
const query = ref('');
const rows = computed(() =>
  (db.data.media || [])
    .filter((m) => !query.value || [m.title, m.pilotId, m.farmId, m.kind].join(' ').toLowerCase().includes(query.value.toLowerCase()))
);
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Медиатека</h1>
        <ManualLink />
        <div class="subtitle">Фото и видео ДО / ПОСЛЕ, материалы для кейсов и соцсетей</div>
      </div>
      <BackendBadge collection="media" />
    
      <button class="btn primary slim" @click="rowOpen = true" title="Добавить запись вручную">＋ Добавить</button>
    </div>

    <div class="toolbar">
      <input v-model="query" class="input" style="max-width:320px" placeholder="Поиск по материалам…" />
    </div>

    <section class="panel">
      <CrmDataTable coll="media" :rows="rows" empty="Материалов нет.">
        <template #actions="{ row: m }">
          <button class="btn slim ghost" @click="openEdit(m)">Изменить</button>
        </template>
      </CrmDataTable>
    </section>
  </div>
  <CrmRowModal v-if="rowOpen" :coll="rowColl" :record="editRec" @close="rowOpen = false; editRec = null" />
</template>

<style scoped>.mini { font-size: 12px; color: var(--muted, #7b8a86); }</style>
