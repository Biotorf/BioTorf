<script setup>
import { DEAL_STAGES, dealStage } from '@/data/crmFields';
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Сделки и воронка» (руководство v0.9 §2, §3 шаг 4): канбан по стадиям +
// таблица сделок; клик — карточка сделки (§5), переход в сквозной процесс.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import CrmImportModal from '@/components/CrmImportModal.vue';
import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';

const rowModal = ref(null);

const importColl = ref('');   // непусто — открыта модалка импорта

const db = useDbStore();
const ui = useUiStore();
const { money, num } = useFormatters();

const deals = computed(() =>
  db.deals.filter((d) => {
    const q = ui.search.toLowerCase();
    if (!q) return true;
    return [d.title, d.owner, d.stage].join(' ').toLowerCase().includes(q);
  })
);

const columns = computed(() => {
  const byStage = new Map(DEAL_STAGES.map((stage) => [stage, []]));
  for (const row of deals.value) {
    const stage = dealStage(row.stage) || 'Без этапа';
    if (!byStage.has(stage)) byStage.set(stage, []);
    byStage.get(stage).push(row);
  }
  return [...byStage].map(([stage, items]) => ({ stage, items }));
});

const totalPipeline = computed(() =>
  deals.value.filter((d) => !['Оплачено', 'Доставка', 'Получено клиентом', 'Завершена'].includes(dealStage(d.stage))).reduce((a, b) => a + (Number(b.amount) || 0), 0)
);

function move(d, dir) {
  if (d.journeyId) return;
  const i = DEAL_STAGES.indexOf(dealStage(d.stage));
  const stage = i < 0 ? DEAL_STAGES[0] : DEAL_STAGES[i + dir];
  if (stage) db.editEntity('deal', d.id, { stage });
}
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Сделки и воронка</h1>
        <ManualLink />
        <div class="subtitle">Открытая воронка: {{ money(totalPipeline) }} · сделок: {{ deals.length }}</div>
      <BackendBadge collection="deals" />
      </div>
      <input :value="ui.search" @input="ui.search = $event.target.value" class="input" style="max-width:260px" placeholder="Поиск по сделкам…" />
      <button class="btn slim" @click="importColl = 'deals'" title="Загрузить сделки из CSV/JSON">⇪ Импорт</button>
      <button class="btn primary slim" @click="rowModal = { coll: 'deals' }">＋ Сделка</button>
    </div>

    <!-- Канбан -->
    <div class="kanban">
      <div v-for="c in columns" :key="c.stage" class="kcol" v-show="c.items.length">
        <div class="khead"><b>{{ c.stage }}</b><span class="mini">{{ c.items.length }}</span></div>
        <div v-for="d in c.items" :key="d.id" class="kcard" @click="ui.openRecord('deal', d.id)">
          <b>{{ d.title }}</b>
          <div class="mini">{{ num(d.volumeL) }} л · {{ money(d.amount) }} · {{ d.owner }}</div>
          <div style="display:flex;gap:6px;margin-top:4px">
            <button v-if="!d.journeyId" class="btn slim" aria-label="Предыдущий этап" @click.stop="move(d, -1)">←</button>
            <button v-if="!d.journeyId" class="btn slim" aria-label="Следующий этап" @click.stop="move(d, 1)">→</button>
            <button v-if="d.journeyId" class="btn slim" @click.stop="ui.openJourney(d.journeyId)">Процесс</button>
          </div>
        </div>
      </div>
      <div v-if="!deals.length" class="empty" style="width:100%">Сделок нет. Создайте лид → квалификацию → сделку в «Сквозном процессе».</div>
    </div>

    <!-- Таблица -->
    <section class="panel" style="margin-top:14px">
      <div class="panel-head"><div class="panel-title">Реестр сделок</div></div>
      <CrmDataTable coll="deals" :rows="deals" empty="Нет сделок по текущему фильтру.">
        <template #actions="{ row: d }">
          <button class="btn slim ghost" @click="ui.openRecord('deal', d.id)">Открыть</button>
          <button v-if="d.journeyId" class="btn slim ghost" @click="ui.openJourney(d.journeyId)">Процесс</button>
          <button class="btn slim ghost" @click="rowModal = { coll: 'deals', record: d }">Изменить</button>
        </template>
      </CrmDataTable>
    </section>

    <CrmImportModal v-if="importColl" :coll="importColl" @close="importColl = ''" />
    <CrmRowModal v-if="rowModal" :coll="rowModal.coll" :record="rowModal.record" @close="rowModal = null" />
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
