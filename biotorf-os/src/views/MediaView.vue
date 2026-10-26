<script setup>
// «Медиатека» (демо v0.9 §8): фото/видео ДО-ПОСЛЕ по пилотам и кейсам.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const { day } = useFormatters();
const query = ref('');
const rows = computed(() =>
  (db.data.media || [])
    .map((m) => ({ ...m, dateStr: (m.date || m.uploadedAt || '').slice(0, 10) }))
    .filter((m) => !query.value || [m.title, m.pilotId, m.farmId, m.kind].join(' ').toLowerCase().includes(query.value.toLowerCase()))
);
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Медиатека</h1>
        <div class="subtitle">Фото и видео ДО / ПОСЛЕ, материалы для кейсов и соцсетей</div>
      </div>
      <BackendBadge collection="media" />
    </div>

    <div class="toolbar">
      <input v-model="query" class="input" style="max-width:320px" placeholder="Поиск по материалам…" />
    </div>

    <section class="panel">
      <table class="table">
        <thead><tr><th>Материал</th><th>Тип</th><th>Пилот / хозяйство</th><th>Дата</th><th>Согласие на публикацию</th></tr></thead>
        <tbody>
          <tr v-for="m in rows" :key="m.id">
            <td><b>{{ m.title || m.file || m.id }}</b><div class="mini">{{ m.note || '' }}</div></td>
            <td><span class="chip neutral">{{ m.kind || 'Фото' }}</span></td>
            <td>{{ m.pilotId || m.farmId || '—' }}</td>
            <td>{{ day(m.dateStr) }}</td>
            <td><span class="pill" :class="m.consent === 'Да' ? '' : 'amber'">{{ m.consent || 'Нет' }}</span></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="5" class="empty">
            Материалов пока нет.<br />
            <span class="mini">Загрузка файлов появится вместе с привязкой к бэкенду; публикация кейсов — только с согласием хозяйства (§8).</span>
          </td></tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>.mini { font-size: 12px; color: var(--muted, #7b8a86); }</style>
