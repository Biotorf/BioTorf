<script setup>
// «Сделки и воронка» (руководство v0.9 §2, §3 шаг 4): канбан по стадиям +
// таблица сделок; клик — карточка сделки (§5), переход в сквозной процесс.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import CrmImportModal from '@/components/CrmImportModal.vue';

const importColl = ref('');   // непусто — открыта модалка импорта

const db = useDbStore();
const ui = useUiStore();
const { money, num } = useFormatters();

const STAGES = ['Новая', 'Квалификация', 'Пилот или КП', 'КП отправлено', 'Счёт выставлен', 'Оплачено', 'Доставка', 'Получено клиентом', 'Завершена'];

const deals = computed(() =>
  db.deals.filter((d) => {
    const q = ui.search.toLowerCase();
    if (!q) return true;
    return [d.title, d.owner, d.stage].join(' ').toLowerCase().includes(q);
  })
);

const columns = computed(() => {
  const cols = STAGES.map((s) => ({ stage: s, items: deals.value.filter((d) => d.stage === s) }));
  const known = new Set(STAGES);
  for (const d of deals.value) if (!known.has(d.stage)) cols.push({ stage: d.stage, items: deals.value.filter((x) => x.stage === d.stage) });
  return cols;
});

const totalPipeline = computed(() =>
  deals.value.filter((d) => !['Оплачено', 'Отгружено', 'Получено клиентом', 'Завершена'].includes(d.stage)).reduce((a, b) => a + (b.amount || 0), 0)
);

function move(d, dir) {
  const i = STAGES.indexOf(d.stage);
  if (i < 0) return;
  const ni = Math.min(STAGES.length - 1, Math.max(0, i + dir));
  db.editEntity('deal', d.id, { stage: STAGES[ni] });
}
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Сделки и воронка</h1>
        <div class="subtitle">Открытая воронка: {{ money(totalPipeline) }} · сделок: {{ deals.length }}</div>
      <BackendBadge collection="deals" />
      </div>
      <input :value="ui.search" @input="ui.search = $event.target.value" class="input" style="max-width:260px" placeholder="Поиск по сделкам…" />
      <button class="btn slim" @click="importColl = 'deals'" title="Загрузить сделки из CSV/JSON">⇪ Импорт</button>
    </div>

    <!-- Канбан -->
    <div class="kanban">
      <div v-for="c in columns" :key="c.stage" class="kcol" v-show="c.items.length">
        <div class="khead"><b>{{ c.stage }}</b><span class="mini">{{ c.items.length }}</span></div>
        <div v-for="d in c.items" :key="d.id" class="kcard" @click="ui.openRecord('deal', d.id)">
          <b>{{ d.title }}</b>
          <div class="mini">{{ num(d.volumeL) }} л · {{ money(d.amount) }} · {{ d.owner }}</div>
          <div style="display:flex;gap:6px;margin-top:4px">
            <button class="btn slim" @click.stop="move(d, -1)">←</button>
            <button class="btn slim" @click.stop="move(d, 1)">→</button>
            <button v-if="d.journeyId" class="btn slim" @click.stop="ui.openJourney(d.journeyId)">Процесс</button>
          </div>
        </div>
      </div>
      <div v-if="!deals.length" class="empty" style="width:100%">Сделок нет. Создайте лид → квалификацию → сделку в «Сквозном процессе».</div>
    </div>

    <!-- Таблица -->
    <section class="panel" style="margin-top:14px">
      <div class="panel-head"><div class="panel-title">Реестр сделок</div></div>
      <table class="table">
        <thead><tr><th>Сделка</th><th>Стадия</th><th>Объём, л</th><th>Сумма</th><th>Ответственный</th><th></th></tr></thead>
        <tbody>
          <tr v-for="d in deals" :key="d.id" class="row-click" @click="ui.openRecord('deal', d.id)">
            <td><b>{{ d.title }}</b></td>
            <td><StatusPill :status="d.stage" /></td>
            <td>{{ num(d.volumeL) }}</td>
            <td>{{ money(d.amount) }}</td>
            <td>{{ d.owner }}</td>
            <td><button v-if="d.journeyId" class="btn slim" @click.stop="ui.openJourney(d.journeyId)">Открыть процесс</button></td>
          </tr>
          <tr v-if="!deals.length"><td colspan="6" class="empty">Нет сделок по текущему фильтру</td></tr>
        </tbody>
      </table>
    </section>

    <CrmImportModal v-if="importColl" :coll="importColl" @close="importColl = ''" />
  </div>
</template>

<style scoped>
.kanban { display: flex; gap: 10px; overflow-x: auto; align-items: flex-start; }
.kcol { min-width: 220px; max-width: 260px; background: #f3f4f6; border-radius: 8px; padding: 8px; }
.khead { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px; }
.kcard { background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px; margin-bottom: 6px; cursor: pointer; font-size: 13px; }
.kcard:hover { border-color: #1f7a3f; }
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
</style>
