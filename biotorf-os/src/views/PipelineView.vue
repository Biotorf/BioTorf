<script setup>
import { DEAL_STAGES, dealStage } from '@/data/crmFields';
import CrmDataTable from '@/components/CrmDataTable.vue';
// «Сделки и воронка» (руководство v0.9 §2, §3 шаг 4): канбан по стадиям +
// таблица сделок; клик — карточка сделки (§5), переход в сквозной процесс.
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { usePermissions } from '@/composables/usePermissions';
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
const { money, num, day } = useFormatters();
const { canEditCollection, canSeeFarm } = usePermissions();
const mode = ref('board');
const owner = ref('');
const availableDeals = computed(() => db.deals.filter((deal) => {
  const client = db.farmById(deal.farmId);
  return !client || canSeeFarm(client);
}));
const owners = computed(() => [...new Set(availableDeals.value.map(({ owner }) => owner).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru')));
const deals = computed(() => {
  const query = ui.search.trim().toLowerCase();
  return availableDeals.value.filter((deal) => (!owner.value || deal.owner === owner.value) &&
    (!query || [deal.title, deal.owner, dealStage(deal.stage), db.farmById(deal.farmId)?.name].join(' ').toLowerCase().includes(query)));
});

const columns = computed(() => {
  const byStage = new Map(DEAL_STAGES.map((stage) => [stage, []]));
  for (const row of deals.value) {
    const stage = dealStage(row.stage) || 'Без этапа';
    if (!byStage.has(stage)) byStage.set(stage, []);
    byStage.get(stage).push(row);
  }
  return [...byStage].filter(([, items]) => items.length).map(([stage, items]) => ({
    stage, items: items.slice().sort((a, b) => String(a.next || '9999').localeCompare(String(b.next || '9999'))),
    amount: items.reduce((sum, item) => sum + (Number(item.amount) || 0), 0),
  }));
});

const totalPipeline = computed(() =>
  deals.value.filter((d) => !['Оплачено', 'Доставка', 'Получено клиентом', 'Завершена'].includes(dealStage(d.stage))).reduce((a, b) => a + (Number(b.amount) || 0), 0)
);

function move(d, dir) {
  if (d.journeyId || !canEditCollection('deals')) return;
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
      <div v-if="canEditCollection('deals')" class="actionbar">
        <button type="button" class="btn slim" @click="importColl = 'deals'">Импорт</button>
        <button type="button" class="btn primary slim" @click="rowModal = { coll: 'deals' }">＋ Сделка</button>
      </div>
    </div>

    <CrmRowModal
      v-if="rowModal"
      inline
      :key="rowModal.record?.id || 'new'"
      :coll="rowModal.coll"
      :record="rowModal.record"
      @close="rowModal = null"
    />

    <div class="toolbar deal-tools">
      <input v-model="ui.search" class="input" type="search" placeholder="Название, клиент, этап" aria-label="Поиск сделки" />
      <select v-model="owner" class="select" aria-label="Ответственный">
        <option value="">Все ответственные</option>
        <option v-for="name in owners" :key="name">{{ name }}</option>
      </select>
      <div class="actionbar" aria-label="Вид сделок">
        <button class="btn slim" :class="{ primary: mode === 'board' }" :aria-pressed="mode === 'board'" @click="mode = 'board'">Доска</button>
        <button class="btn slim" :class="{ primary: mode === 'list' }" :aria-pressed="mode === 'list'" @click="mode = 'list'">Список</button>
      </div>
    </div>
    <!-- Канбан -->
    <div v-if="mode === 'board'" class="kanban" tabindex="0" aria-label="Доска по этапам">
      <div v-for="c in columns" :key="c.stage" class="kcol">
        <div class="khead"><strong>{{ c.stage }}</strong><span class="mini">{{ c.items.length }} · {{ money(c.amount) }}</span></div>
        <article v-for="d in c.items" :key="d.id" class="kcard">
          <a v-if="d.journeyId" :href="'#/journey?id=' + encodeURIComponent(d.journeyId)">{{ d.title }}</a>
          <button v-else type="button" class="open-deal" @click="ui.openRecord('deal', d.id)">{{ d.title }}</button>
          <div class="mini">{{ num(d.volumeL) }} л · {{ money(d.amount) }} · {{ d.owner }}</div>
          <div v-if="d.next" class="mini">Следующий контакт {{ day(d.next) }}</div>
          <div v-if="canEditCollection('deals') && !d.journeyId" class="actionbar" style="margin-top:4px">
            <button class="btn slim" aria-label="Предыдущий этап" @click.stop="move(d, -1)">←</button>
            <button class="btn slim" aria-label="Следующий этап" @click.stop="move(d, 1)">→</button>
          </div>
        </article>
      </div>
      <div v-if="!deals.length" class="empty" style="width:100%">Сделок по этим условиям нет.</div>
    </div>

    <section v-else class="panel">
      <div class="panel-head"><div class="panel-title">Реестр сделок</div></div>
      <CrmDataTable coll="deals" :rows="deals" empty="Нет сделок по текущему фильтру.">
        <template #actions="{ row: d }">
          <button class="btn slim ghost" @click="ui.openRecord('deal', d.id)">Открыть</button>
          <button v-if="d.journeyId" class="btn slim ghost" @click="ui.openJourney(d.journeyId)">Процесс</button>
          <button v-if="canEditCollection('deals')" class="btn slim ghost" @click="rowModal = { coll: 'deals', record: d }">Изменить</button>
        </template>
      </CrmDataTable>
    </section>

    <CrmImportModal v-if="importColl" :coll="importColl" @close="importColl = ''" />
  </div>
</template>

<style scoped>
.kanban { display: flex; gap: 10px; overflow-x: auto; align-items: flex-start; }
.kcol { min-width: 220px; max-width: 260px; background: #f3f4f6; border-radius: 8px; padding: 8px; }
.khead { display: grid; margin-bottom: 8px; gap: 3px; font-size: 13px; }
.kcard { background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px; margin-bottom: 6px; font-size: 13px; }
.kcard:hover { border-color: #1f7a3f; }
.deal-tools { justify-content: flex-start; }
.deal-tools .select { max-width: 215px; }
.kcard > a, .open-deal { font-weight: 720; display: inline-block; margin-bottom: 3px; }
.open-deal { background: transparent; border: 0; padding: 0; color: var(--green); text-align: start; }
</style>
