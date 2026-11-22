<script setup>
import CrmDataTable from '@/components/CrmDataTable.vue';
// «База знаний» (руководство v0.9 §8): проверенные схемы применения и регламенты.
// Демо-версия из BIOTORF_Business_OS_demo_v0.9.html; привязка к бэкенду — позже.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import BackendBadge from '@/components/ui/BackendBadge.vue';

import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
const rowColl = ref('knowledge');
const rowOpen = ref(false);
const editRec = ref(null);
function openEdit(rec) { editRec.value = rec; rowOpen.value = true; }

const db = useDbStore();
const query = ref('');
const cat = ref('Все');

const cats = computed(() => ['Все', ...new Set((db.knowledge || []).map((k) => k.category))]);
const items = computed(() =>
  (db.knowledge || [])
    .filter((k) => cat.value === 'Все' || k.category === cat.value)
    .filter((k) => !query.value || [k.title, k.text ?? k.summary, k.crop].join(' ').toLowerCase().includes(query.value.toLowerCase()))
);
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>База знаний</h1>
        <ManualLink />
        <div class="subtitle">Проверенные схемы применения, регламенты и скрипты продаж</div>
      </div>
      <BackendBadge collection="knowledge" />
    
      <button class="btn primary slim" @click="rowOpen = true" title="Добавить запись вручную">＋ Добавить</button>
    </div>

    <div class="toolbar">
      <input v-model="query" class="input" placeholder="Поиск по статьям…" style="max-width:340px" />
      <select v-model="cat" class="select" style="max-width:220px"><option v-for="c in cats" :key="c">{{ c }}</option></select>
    </div>

    <section class="panel">
      <CrmDataTable coll="knowledge" :rows="items" empty="Статей не найдено.">
        <template #actions="{ row: k }">
          <button class="btn slim ghost" @click="openEdit(k)">Изменить</button>
        </template>
      </CrmDataTable>
    </section>
  </div>
  <CrmRowModal v-if="rowOpen" :coll="rowColl" :record="editRec" @close="rowOpen = false; editRec = null" />
</template>
