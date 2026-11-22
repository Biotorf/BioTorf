<script setup>
import CrmDataTable from '@/components/CrmDataTable.vue';
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import CrmImportModal from '@/components/CrmImportModal.vue';
import CrmRowModal from '@/components/CrmRowModal.vue';
import ManualLink from '@/components/ui/ManualLink.vue';

const rowModal = ref(null);   // { coll, record? } — ручное добавление/редактирование

const importColl = ref('');   // непусто — открыта модалка импорта этой таблицы

const db = useDbStore();
const ui = useUiStore();
const { canSeeFarm } = usePermissions();

const farms = computed(() =>
  db.farms
    .filter(canSeeFarm)
    .filter((f) => {
      const q = ui.search.toLowerCase();
      if (!q) return true;
      return [f.name, f.region, f.crop, f.owner, f.status]
        .join(' ').toLowerCase().includes(q);
    })
);

// Входящие обращения (руководство v0.9 §3 шаг 1): поиск + фильтр статуса
const leadQ = ref('');
const leadStatus = ref('Все');
const LEAD_STATUSES = ['Все', 'Новый лид', 'В работе', 'Квалифицирован', 'Сделка создана', 'Отказ'];
const leads = computed(() =>
  db.leads
    .filter((l) => leadStatus.value === 'Все' || l.status === leadStatus.value)
    .filter((l) => {
      const q = leadQ.value.toLowerCase();
      if (!q) return true;
      return [l.name, l.contactName, l.phone, l.company, l.region, l.source, l.owner, l.status]
        .join(' ').toLowerCase().includes(q);
    })
);

const commsUnread = (farmId) => db.comms.filter((c) => c.farmId === farmId && !c.read).length;
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Клиенты и хозяйства</h1>
        <ManualLink />
        <div class="subtitle">Реестр хозяйств, контактов и входящих лидов</div>
      </div>
      <div class="actionbar">
        <BackendBadge collection="farms" />
        <button class="btn slim" @click="importColl = 'farms'" title="Загрузить хозяйства из CSV/JSON">⇪ Импорт · Хозяйства</button>
        <button class="btn slim" @click="importColl = 'leads'" title="Загрузить лиды из CSV/JSON">⇪ Импорт · Лиды</button>
        <button class="btn primary slim" @click="rowModal = { coll: 'farms' }">＋ Хозяйство</button>
        <button class="btn primary slim" @click="rowModal = { coll: 'leads' }">＋ Лид</button>
      </div>
    </div>

    <!-- Входящие обращения -->
    <div class="insight" style="margin-bottom:14px;flex-wrap:wrap;gap:8px">
      <b>Входящие обращения</b>
      <input v-model="leadQ" class="input" style="max-width:260px" placeholder="Поиск по теме, контакту, региону…" />
      <select v-model="leadStatus" class="select" style="max-width:200px">
        <option v-for="s in LEAD_STATUSES" :key="s">{{ s }}</option>
      </select>
      <span class="mini">{{ leads.length }} записей</span>
    </div>
    <div class="table-wrap" style="margin-bottom:18px">
      <CrmDataTable coll="leads" :rows="leads" empty="Нет входящих обращений по текущему фильтру.">
        <template #actions="{ row: l }">
          <button class="btn slim ghost" @click="ui.openLeadCard(l.id)">Открыть лид</button>
          <button class="btn slim ghost" @click="rowModal = { coll: 'leads', record: l }">Изменить</button>
        </template>
      </CrmDataTable>
    </div>

    <div class="table-wrap">
      <CrmDataTable coll="farms" :rows="farms" empty="Хозяйств нет.">
        <template #actions="{ row: f }">
          <button class="btn slim ghost" @click="ui.openClient(f.id)">Карточка клиента</button>
          <button class="btn slim ghost" @click="ui.openComms(f.id)">Переписка<template v-if="commsUnread(f.id)"> · {{ commsUnread(f.id) }}</template></button>
          <button class="btn slim ghost" @click="rowModal = { coll: 'farms', record: f }">Изменить</button>
        </template>
      </CrmDataTable>
    </div>

    <CrmImportModal v-if="importColl" :coll="importColl" @close="importColl = ''" />
    <CrmRowModal v-if="rowModal" :coll="rowModal.coll" :record="rowModal.record" @close="rowModal = null" />
  </div>
</template>