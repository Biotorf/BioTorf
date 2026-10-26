<script setup>
// «База знаний» (руководство v0.9 §8): проверенные схемы применения и регламенты.
// Демо-версия из BIOTORF_Business_OS_demo_v0.9.html; привязка к бэкенду — позже.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const query = ref('');
const cat = ref('Все');

const cats = computed(() => ['Все', ...new Set((db.knowledge || []).map((k) => k.category))]);
const items = computed(() =>
  (db.knowledge || [])
    .filter((k) => cat.value === 'Все' || k.category === cat.value)
    .filter((k) => !query.value || [k.title, k.summary, k.crop].join(' ').toLowerCase().includes(query.value.toLowerCase()))
);
const openId = ref(null);
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>База знаний</h1>
        <div class="subtitle">Проверенные схемы применения, регламенты и скрипты продаж</div>
      </div>
      <BackendBadge collection="knowledge" />
    </div>

    <div class="toolbar">
      <input v-model="query" class="input" placeholder="Поиск по статьям…" style="max-width:340px" />
      <select v-model="cat" class="select" style="max-width:220px"><option v-for="c in cats" :key="c">{{ c }}</option></select>
    </div>

    <section class="panel">
      <table class="table">
        <thead><tr><th>Статья</th><th>Категория</th><th>Культура</th><th>Версия</th><th>Ответственный</th><th>Статус</th></tr></thead>
        <tbody>
          <template v-for="k in items" :key="k.id">
            <tr class="row-click" @click="openId = openId === k.id ? null : k.id">
              <td><b>{{ k.title }}</b><div class="mini">{{ k.id }} · {{ k.source }}</div></td>
              <td><span class="chip neutral">{{ k.category }}</span></td>
              <td>{{ k.crop }}</td>
              <td>v{{ k.version }}</td>
              <td>{{ k.owner }}</td>
              <td><StatusPill :status="k.status" /></td>
            </tr>
            <tr v-if="openId === k.id"><td colspan="6" style="white-space:normal;background:#f7faf8">
              <div class="kb-text">{{ k.summary }}</div>
              <div class="mini" style="margin-top:8px">{{ k.public ? '🌐 Материал для публичного использования' : '🔒 Только для внутреннего использования' }}</div>
            </td></tr>
          </template>
          <tr v-if="!items.length"><td colspan="6" class="empty">Статей не найдено.</td></tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
.kb-text { color: #597269; line-height: 1.65; }
.mini { font-size: 12px; color: var(--muted, #7b8a86); }
</style>
