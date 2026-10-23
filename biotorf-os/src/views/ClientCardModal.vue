<script setup>
import { ref, computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';

const props = defineProps({ farmId: { type: String, required: true } });
const db = useDbStore();
const { num, day, money } = useFormatters();

const tabs = ['overview', 'contacts', 'comms', 'deals', 'pilots', 'orders', 'history'];
const active = ref('overview');

const farm = computed(() => db.farmById(props.farmId));
const contacts = computed(() => db.data.contacts.filter((c) => c.farmId === props.farmId));
const deals = computed(() => db.deals.filter((d) => d.farmId === props.farmId));
const pilots = computed(() => db.pilots.filter((p) => p.farmId === props.farmId));
const orders = computed(() => db.orders.filter((o) => o.farmId === props.farmId));
const comms = computed(() =>
  (db.comms || [])
    .filter((c) => c.farmId === props.farmId)
    .sort((a, b) => (a.ts < b.ts ? 1 : -1))
);

const KIND_ICON = { call: '☎', telegram: '✈', whatsapp: '◔' };
function fmtCommTs(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU') + ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

// быстрый ответ прямо из карточки клиента
const replyText = ref('');
const replyKind = ref('telegram');
function sendFromCard() {
  if (!replyText.value.trim()) return;
  db.addComm({
    kind: replyKind.value,
    dir: 'out',
    farmId: props.farmId,
    contact: farm.value?.owner || null,
    phone: farm.value?.phone || null,
    text: replyText.value.trim(),
    read: true,
  });
  replyText.value = '';
}
</script>

<template>
  <div v-if="farm">
    <div class="client-hero">
      <div>
        <div class="mini">КАРТОЧКА КЛИЕНТА · {{ farm.id }}</div>
        <h3>{{ farm.name }}</h3>
        <div class="mini">{{ farm.region }} · {{ farm.crop }} · {{ num(farm.area) }} га</div>
      </div>
      <StatusPill :status="farm.status" />
    </div>

    <div class="client-tabs">
      <button
        v-for="t in tabs"
        :key="t"
        class="client-tab"
        :class="{ selected: active === t }"
        @click="active = t"
      >
        {{ { overview: 'Обзор', contacts: 'Контакты', comms: `Связь (${comms.length})`, deals: 'Сделки', pilots: 'Испытания', orders: 'Заказы', history: 'История' }[t] }}
      </button>
    </div>

    <div v-if="active === 'comms'">
      <div class="toolbar" style="margin-bottom:10px">
        <span class="mini">Вся переписка и звонки по этому клиенту — в сервисе, без телефона и внешних мессенджеров.</span>
      </div>
      <div v-for="c in comms" :key="c.id" class="insight">
        <div style="min-width:0">
          <b>{{ KIND_ICON[c.kind] }} {{ c.dir === 'in' ? '↓ Входящее' : '↑ Исходящее' }}</b>
          <div class="mini">{{ fmtCommTs(c.ts) }} · {{ c.contact || c.phone || c.handle || '—' }}</div>
          <div v-if="c.kind === 'call'" class="mini">{{ c.status }}{{ c.duration ? ' · ' + Math.round(c.duration / 60) + ' мин' : '' }} — {{ c.note }}</div>
          <div v-else class="comms-bubble-card" :class="{ out: c.dir === 'out' }">{{ c.text }}</div>
        </div>
      </div>
      <div v-if="!comms.length" class="empty">Связь с этим клиентом ещё не фиксировалась</div>

      <div class="muted-block" style="margin-top:14px">
        <div class="field">
          <label>Быстрый ответ клиенту</label>
          <div style="display:flex;gap:8px;margin-bottom:8px">
            <select v-model="replyKind" class="select" style="max-width:160px">
              <option value="telegram">Telegram</option>
              <option value="whatsapp">WhatsApp</option>
            </select>
          </div>
          <textarea v-model="replyText" class="textarea" rows="3" placeholder="Текст сообщения…"></textarea>
        </div>
        <div class="actionbar" style="margin-top:10px">
          <button class="btn primary slim" :disabled="!replyText.trim()" @click="sendFromCard">Отправить (в ленту)</button>
        </div>
      </div>
    </div>

    <div v-if="active === 'overview'" class="details-grid">
      <dl class="detail"><dt>Тип</dt><dd>{{ farm.type }}</dd></dl>
      <dl class="detail"><dt>Менеджер</dt><dd>{{ farm.owner }}</dd></dl>
      <dl class="detail"><dt>Следующий контакт</dt><dd>{{ day(farm.next) }}</dd></dl>
      <dl class="detail"><dt>Площадь</dt><dd>{{ num(farm.area) }} га</dd></dl>
    </div>

    <div v-if="active === 'deals'">
      <div v-for="d in deals" :key="d.id" class="insight">
        <div><b>{{ d.title }}</b><div class="mini">{{ d.stage }}</div></div>
        <b>{{ money(d.amount) }}</b>
      </div>
      <div v-if="!deals.length" class="empty">Сделок нет</div>
    </div>

    <div v-if="active === 'pilots'">
      <div v-for="p in pilots" :key="p.id" class="insight">
        <div><b>{{ p.crop }}</b><div class="mini">{{ p.id }} · {{ num(p.area) }} га</div></div>
        <StatusPill :status="p.status" />
      </div>
      <div v-if="!pilots.length" class="empty">Испытаний нет</div>
    </div>

    <div v-if="active === 'orders'">
      <div v-for="o in orders" :key="o.id" class="insight">
        <div><b>{{ o.id }}</b><div class="mini">{{ o.status }}</div></div>
        <b>{{ money(o.amount) }}</b>
      </div>
      <div v-if="!orders.length" class="empty">Заказов нет</div>
    </div>
  </div>
</template>

<style scoped>
.comms-bubble-card { background:#f1f6f3; border:1px solid #e0ebe4; border-radius:10px; padding:8px 11px; font-size:13px; margin-top:5px; }
.comms-bubble-card.out { background:#e2f6e8; border-color:#cdecd6; }
</style>