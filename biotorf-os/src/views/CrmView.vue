<script setup>
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const ui = useUiStore();
const { canSeeFarm } = usePermissions();
const { num, day } = useFormatters();

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
const journeyOf = (leadId) => db.journeys.find((j) => j.leadId === leadId);

const commsCount = (farmId) => db.comms.filter((c) => c.farmId === farmId).length;
const commsUnread = (farmId) => db.comms.filter((c) => c.farmId === farmId && !c.read).length;
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Клиенты и хозяйства</h1>
        <div class="subtitle">Реестр хозяйств, контактов и входящих лидов</div>
      </div>
      <BackendBadge collection="farms" />
      <button class="btn primary slim" @click="ui.go('journey')">＋ Создать · Лид</button>
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
      <table class="table">
        <thead>
          <tr>
            <th>Тема обращения</th>
            <th>Контакт / телефон</th>
            <th>Компания / регион</th>
            <th>Источник</th>
            <th>Ответственный</th>
            <th>Статус</th>
            <th>Следующий контакт</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in leads" :key="l.id" class="clickrow" @click="ui.openLeadCard(l.id)">
            <td>
              <span class="txt-link">{{ l.name }}</span>
              <div class="mini">{{ l.id }}<template v-if="l.farmId"> · хозяйство {{ l.farmId }}</template><template v-else> · Не известно / создадим при квалификации</template></div>
            </td>
            <td>{{ l.contactName || '—' }}<div class="mini">{{ l.phone || '' }}</div></td>
            <td>{{ l.company || '—' }}<div class="mini">{{ l.region || '' }}</div></td>
            <td>{{ l.source || '—' }}</td>
            <td>{{ l.owner }}</td>
            <td><StatusPill :status="l.status" /></td>
            <td>{{ day(l.next) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!leads.length" class="empty">Нет входящих обращений по текущему фильтру.</div>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Клиент / хозяйство</th>
            <th>Регион</th>
            <th>Культура</th>
            <th>Площадь</th>
            <th>Менеджер</th>
            <th>Статус</th>
            <th>След. контакт</th>
            <th>Связь</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="f in farms"
            :key="f.id"
            class="clickrow"
            @click="ui.openClient(f.id)"
          >
            <td>
              <span class="txt-link">{{ f.name }}</span>
              <div class="mini">{{ f.type }} · {{ f.id }}</div>
            </td>
            <td>{{ f.region }}</td>
            <td>{{ f.crop }}</td>
            <td>{{ num(f.area) }} га</td>
            <td>{{ f.owner }}</td>
            <td><StatusPill :status="f.status" /></td>
            <td>{{ day(f.next) }}</td>
            <td @click.stop>
              <button class="btn slim ghost" title="Открыть переписку и звонки" @click="ui.openComms(f.id)">
                ☎ {{ commsCount(f.id) }}<template v-if="commsUnread(f.id)"> · <span class="pill red">{{ commsUnread(f.id) }}</span></template>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>