<script setup>
// «Маркетинг и соцсети» (демо v0.9 §8): контент-план публикаций, привязка к пилотам,
// согласование. Прямые публикации в Instagram в v0.9 не выполняются.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const ui = useUiStore();
const { day } = useFormatters();
const statusFilter = ref('Все');
const monthShort = (d) => (d ? new Date(d + 'T12:00:00').toLocaleDateString('ru-RU', { month: 'short' }).replace('.', '') : '');
const rows = computed(() =>
  (db.social || [])
    .filter((s) => statusFilter.value === 'Все' || s.status === statusFilter.value)
    .slice().sort((a, b) => ((a.date || '') > (b.date || '') ? 1 : -1))
);
const STATUSES = ['Все', 'Черновик', 'На согласовании', 'Готово к публикации', 'Опубликовано'];
const pilotTitle = (pid) => {
  if (!pid || pid === 'Без привязки') return 'Без привязки';
  const p = db.pilotById(pid);
  return p ? `${p.crop || pid} · ${p.id}` : pid;
};
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Маркетинг и соцсети</h1>
        <div class="subtitle">Контент-план публикаций, связь с пилотами и согласование</div>
      </div>
      <BackendBadge collection="social" />
    </div>

    <div class="note">В v0.9 публикации в Instagram автоматически не отправляются; результаты пилотов публикуются только после проверки агрономом и согласия хозяйства.</div>

    <div class="toolbar">
      <select v-model="statusFilter" class="select" style="max-width:240px"><option v-for="s in STATUSES" :key="s">{{ s }}</option></select>
    </div>

    <div class="social-calendar">
      <article v-for="s in rows" :key="s.id" class="calendar-item actionable" @click="s.pilotId && s.pilotId !== 'Без привязки' ? ui.openRecord('pilot', s.pilotId) : null">
        <div class="calendar-day">{{ (s.date || '').slice(8, 10) || '—' }}<small>{{ monthShort(s.date) }}</small></div>
        <div style="min-width:0">
          <b>{{ s.title }}</b>
          <div class="mini">{{ s.channel }} · {{ s.kind }} · пилот: {{ pilotTitle(s.pilotId) }}</div>
          <div class="mini">Согласие на кейс: {{ s.consent }} · Кейс утверждён: {{ s.caseApproved }} · {{ s.owner }}</div>
        </div>
        <StatusPill :status="s.status" class="ml-auto" />
      </article>
      <div v-if="!rows.length" class="empty">Публикаций нет.</div>
    </div>
  </div>
</template>


<style scoped>
.social-calendar { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.calendar-item { display: flex; align-items: center; gap: 12px; border: 1px solid #e6ede8; border-radius: 12px; padding: 10px; background: #fff; }
.calendar-day { border-radius: 9px; background: #ecf9ee; min-width: 48px; padding: 7px; text-align: center; color: #257747; font-weight: 800; font-size: 18px; }
.calendar-day small { display: block; font-size: 10px; font-weight: 500; }
.actionable { cursor: pointer; }
.ml-auto { margin-left: auto; }
.mini { font-size: 12px; color: var(--muted, #7b8a86); }
@media (max-width: 800px) { .social-calendar { grid-template-columns: 1fr; } }
</style>
