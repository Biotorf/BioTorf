<script setup>
import { computed, onMounted, ref } from 'vue';
import { useDbStore, isLate } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import { crmTitle, crmValue } from '@/data/crmFields';
import CrmRowModal from '@/components/CrmRowModal.vue';
import StatusPill from '@/components/ui/StatusPill.vue';

const props = defineProps({
  farmId: { type: String, required: true },
  embedded: { type: Boolean, default: false },
});
const db = useDbStore();
const ui = useUiStore();
const { canEditCollection, canSeeFarm } = usePermissions();
const { day, money } = useFormatters();

onMounted(() => db.syncComms(true));
const farm = computed(() => {
  const entry = db.farmById(props.farmId);
  return entry && canSeeFarm(entry) ? entry : null;
});
const clientRecords = (collection) => computed(() =>
  (db.data[collection] || []).filter((record) => String(record.farmId) === props.farmId));
function shownDate(value) {
  if (!value) return '—';
  if (String(value).length === 10) return day(value);
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString('ru-RU', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
const contacts = clientRecords('contacts');
const deals = clientRecords('deals');
const pilots = clientRecords('pilots');
const orders = clientRecords('orders');
const leads = clientRecords('leads');
const comms = clientRecords('comms');
const notes = clientRecords('clientNotes');
const journeys = clientRecords('journeys');
const shipments = clientRecords('shipments');
const invoices = computed(() => (db.data.invoices || []).filter((record) => record.farmId === props.farmId ||
  orders.value.some((order) => order.id === record.orderId)));
const relatedIds = computed(() => ({
  farm: [props.farmId],
  lead: leads.value.map(({ id }) => id),
  journey: journeys.value.map(({ id }) => id),
  deal: deals.value.map(({ id }) => id),
  pilot: pilots.value.map(({ id }) => id),
  order: orders.value.map(({ id }) => id),
  invoice: invoices.value.map(({ id }) => id),
  shipment: shipments.value.map(({ id }) => id),
}));
const tasks = computed(() => (db.data.tasks || []).filter((task) => relatedIds.value[task.refKind]?.includes(task.refId)));
const nextAction = computed(() => tasks.value
  .filter((task) => !['Выполнена', 'Отменена', 'Закрыта'].includes(task.status))
  .sort((first, second) => (first.due || '9999').localeCompare(second.due || '9999'))[0]);
const primaryContact = computed(() => contacts.value.find((contact) => contact.primary) || contacts.value[0]);

const tabs = [
  { id: 'history', label: 'История' },
  { id: 'sales', label: 'Продажи' },
  { id: 'contacts', label: 'Контакты' },
];
const active = ref('history');
const noteText = ref('');
const planning = ref(false);
const action = ref({ title: '', due: '', owner: '' });
const starting = ref(false);
const cardError = ref('');
const edit = ref(null);

const channelNames = { call: 'Звонок', telegram: 'Telegram', whatsapp: 'WhatsApp', email: 'Почта' };
const timeline = computed(() => {
  const entries = [];
  for (const item of comms.value) {
    const direction = item.dir === 'in' ? 'входящий' : 'исходящий';
    entries.push({
      id: 'comm:' + item.id, date: item.ts,
      title: (channelNames[item.kind] || item.kind || 'Связь') + ' · ' + direction,
      text: item.text || item.note || item.status || item.contact || '',
    });
  }
  for (const item of notes.value) {
    if (/^hist:/.test(item.id) && comms.value.some((message) => 'hist:' + message.id === item.id)) continue;
    entries.push({ id: 'note:' + item.id, date: item.ts || item.date, title: 'Заметка', text: item.text });
  }
  if (farm.value) {
    const text = crmValue('farms', farm.value, 'notes');
    if (text) entries.push({ id: 'farm:notes', date: '', title: 'Заметки о клиенте', text });
  }
  for (const item of tasks.value) {
    entries.push({
      id: 'task:' + item.id, date: item.createdAt || item.due,
      title: 'Задача · ' + item.title,
      text: [item.owner, item.status, item.due && 'до ' + day(item.due)].filter(Boolean).join(' · '),
    });
  }
  for (const [type, records] of [['Сделка', deals.value], ['Заказ', orders.value], ['Отгрузка', shipments.value]]) {
    for (const record of records) {
      entries.push({
        id: type + ':' + record.id, date: record.date || record.createdAt,
        title: type + ' · ' + crmTitle(record), text: record.stage || record.status,
      });
    }
  }
  return entries.sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
});

function openComms() {
  if (!props.embedded) ui.closeModal();
  ui.openComms(props.farmId);
}
function openJourney(id) {
  if (!props.embedded) ui.closeModal();
  ui.openJourney(id);
}
function recordUrl(table, id) {
  return '#/registry?' + new URLSearchParams({ table, id });
}
function openScheduling() {
  action.value = { title: '', due: '', owner: farm.value?.owner || ui.name || ui.login };
  planning.value = true;
}
function scheduleAction() {
  const title = action.value.title.trim();
  if (!title) return;
  db.addTask({
    title, owner: action.value.owner.trim(), due: action.value.due || null,
    priority: 'Средний', refKind: 'farm', refId: props.farmId, status: 'Открыта',
  });
  planning.value = false;
}
function completeNextAction() {
  if (nextAction.value) db.updateTask(nextAction.value.id, { status: 'Выполнена' });
}
function saveNote() {
  const value = noteText.value.trim();
  if (!value) return;
  db.addClientNote(props.farmId, value);
  noteText.value = '';
}
async function startSale() {
  if (starting.value || !farm.value) return;
  starting.value = true;
  cardError.value = '';
  try {
    const id = db.uid('L');
    await db.importCollection('leads', [{
      id, name: 'Запрос · ' + farm.value.name, farmId: props.farmId,
      contactName: primaryContact.value?.name || '', phone: farm.value.phone || primaryContact.value?.phone || '',
      owner: farm.value.owner || ui.name || ui.login, source: 'Карточка клиента', status: 'Новый лид',
      date: new Date().toISOString().slice(0, 10),
    }], 'merge');
    const journey = db.createJourneyFromLead(id);
    if (journey) openJourney(journey.id);
  } catch (error) {
    cardError.value = error.message || 'Не удалось начать продажу.';
  } finally {
    starting.value = false;
  }
}
</script>

<template>
  <article v-if="farm" class="client-card">
    <header class="client-summary">
      <div>
        <div class="client-type">{{ [farm.type, farm.region].filter(Boolean).join(' · ') || 'Клиент' }}</div>
        <component :is="embedded ? 'h1' : 'h2'">{{ farm.name || farm.id }}</component>
        <div class="client-meta">
          <StatusPill v-if="farm.status" :status="farm.status" />
          <span v-if="farm.owner">Менеджер · {{ farm.owner }}</span>
          <a v-if="farm.phone || primaryContact?.phone" :href="'tel:' + (farm.phone || primaryContact.phone)">{{ farm.phone || primaryContact.phone }}</a>
        </div>
      </div>
      <div class="client-actions">
        <button class="btn" @click="openComms">Переписка и звонки</button>
        <button v-if="canEditCollection('farms')" class="btn ghost" @click="edit = { coll: 'farms', record: farm }">Изменить</button>
        <button v-if="canEditCollection('leads')" class="btn primary" :disabled="starting" @click="startSale">{{ starting ? 'Открываем…' : 'Новая продажа' }}</button>
      </div>
    </header>
    <p v-if="cardError" class="danger-text" role="alert">{{ cardError }}</p>

    <div class="client-card-grid">
      <section class="client-card-main panel">
        <nav class="customer-tabs" aria-label="Разделы карточки">
          <button v-for="tab in tabs" :key="tab.id" type="button" :aria-pressed="active === tab.id" @click="active = tab.id">{{ tab.label }}</button>
        </nav>
        <div v-if="active === 'history'" class="customer-tab-content">
          <form v-if="canEditCollection('clientNotes')" class="client-note" @submit.prevent="saveNote">
            <label class="field">Заметка
              <textarea v-model="noteText" class="input" rows="2" placeholder="Что обсудили с клиентом?" />
            </label>
            <button class="btn slim" :disabled="!noteText.trim()">Добавить</button>
          </form>
          <ul v-if="timeline.length" class="customer-timeline">
            <li v-for="entry in timeline" :key="entry.id">
              <header><strong>{{ entry.title }}</strong><time v-if="entry.date" :datetime="entry.date">{{ shownDate(entry.date) }}</time></header>
              <p v-if="entry.text">{{ entry.text }}</p>
            </li>
          </ul>
          <p v-else class="client-empty">У клиента пока нет сообщений, звонков или заметок.</p>
        </div>
        <div v-else-if="active === 'sales'" class="customer-tab-content sales-records">
          <div v-if="journeys.length">
            <h3>Процесс продажи</h3>
            <ul class="related-list">
              <li v-for="record in journeys" :key="record.id">
                <div><strong>{{ db.leadById(record.leadId)?.name || record.id }}</strong><span>{{ record.stage }}</span></div>
                <button class="btn slim" @click="openJourney(record.id)">Открыть</button>
              </li>
            </ul>
          </div>
          <div v-for="[table, title, records] in [['leads', 'Обращения', leads], ['deals', 'Сделки', deals], ['orders', 'Заказы', orders], ['invoices', 'Счета', invoices], ['shipments', 'Отгрузки', shipments], ['pilots', 'Пилоты', pilots]]" :key="table">
            <template v-if="records.length">
              <h3>{{ title }}</h3>
              <ul class="related-list">
                <li v-for="record in records" :key="record.id">
                  <div>
                    <strong>{{ crmTitle(record) }}</strong>
                    <span>{{ [record.status || record.stage, record.amount != null ? money(record.amount) : ''].filter(Boolean).join(' · ') }}</span>
                  </div>
                  <a class="btn slim" :href="recordUrl(table, record.id)" @click="!embedded && ui.closeModal()">Открыть</a>
                </li>
              </ul>
            </template>
          </div>
          <p v-if="!journeys.length && !leads.length && !deals.length && !orders.length && !invoices.length && !shipments.length && !pilots.length" class="client-empty">
            Продаж и пилотов пока нет. Новую продажу можно начать вверху карточки.
          </p>
        </div>
        <div v-else class="customer-tab-content">
          <div v-if="canEditCollection('contacts')" class="contact-actions">
            <button class="btn slim" @click="edit = { coll: 'contacts', initial: { farmId: farm.id } }">＋ Контакт</button>
          </div>
          <ul v-if="contacts.length" class="related-list">
            <li v-for="contact in contacts" :key="contact.id">
              <div>
                <strong>{{ contact.name || contact.id }}<span v-if="contact.primary"> · основной</span></strong>
                <span>{{ [contact.role, contact.phone, contact.email].filter(Boolean).join(' · ') }}</span>
              </div>
              <button v-if="canEditCollection('contacts')" class="btn slim" @click="edit = { coll: 'contacts', record: contact }">Изменить</button>
            </li>
          </ul>
          <p v-else class="client-empty">Дополнительных контактов пока нет.</p>
        </div>
      </section>

      <aside class="client-side">
        <section class="panel side-panel">
          <h3>Следующее действие</h3>
          <div v-if="nextAction" class="next-card">
            <strong>{{ nextAction.title }}</strong>
            <span v-if="nextAction.due" :class="{ 'danger-text': isLate(nextAction.due) }">
              {{ isLate(nextAction.due) ? 'Просрочено · ' : 'До ' }}{{ day(nextAction.due) }}
            </span>
            <span v-if="nextAction.owner">{{ nextAction.owner }}</span>
          </div>
          <p v-else class="client-empty">{{ farm.next ? 'Связаться ' + day(farm.next) : 'Действие не назначено.' }}</p>
          <div v-if="!planning && canEditCollection('tasks')" class="client-actions">
            <button v-if="nextAction" class="btn slim" @click="completeNextAction">Выполнено</button>
            <button class="btn slim" @click="openScheduling">Назначить действие</button>
          </div>
          <form v-if="planning" class="next-form" @submit.prevent="scheduleAction">
            <label class="field">Что сделать <input v-model="action.title" class="input" required /></label>
            <label class="field">Ответственный <input v-model="action.owner" class="input" /></label>
            <label class="field">Срок <input v-model="action.due" class="input" type="date" /></label>
            <div class="client-actions">
              <button type="button" class="btn slim" @click="planning = false">Отмена</button>
              <button class="btn primary slim" :disabled="!action.title.trim()">Сохранить</button>
            </div>
          </form>
        </section>
        <section v-if="primaryContact || farm.crop || farm.area" class="panel side-panel">
          <h3>{{ primaryContact ? 'Основной контакт' : 'Хозяйство' }}</h3>
          <div v-if="primaryContact" class="next-card">
            <strong>{{ primaryContact.name }}</strong>
            <span v-if="primaryContact.role">{{ primaryContact.role }}</span>
            <a v-if="primaryContact.email" :href="'mailto:' + primaryContact.email">{{ primaryContact.email }}</a>
          </div>
          <p v-if="farm.crop || farm.area" class="client-empty">{{ [farm.crop, farm.area && farm.area + ' га'].filter(Boolean).join(' · ') }}</p>
        </section>
      </aside>
    </div>
    <Teleport to="body">
      <CrmRowModal v-if="edit" :coll="edit.coll" :record="edit.record" :initial-values="edit.initial" @close="edit = null" />
    </Teleport>
  </article>
  <p v-else class="empty">Карточка клиента недоступна.</p>
</template>

<style scoped>
.client-summary { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; background: #f1f8f3; border: 1px solid #d7e9dc; border-radius: 14px; padding: 18px; margin-bottom: 14px; }
.client-summary h1, .client-summary h2 { margin: 3px 0 7px; font-size: clamp(20px, 3vw, 27px); overflow-wrap: anywhere; }
.client-type, .client-meta { color: #52665b; font-size: 13px; }
.client-meta, .client-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.client-card-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(190px, 27%); gap: 12px; align-items: start; }
.client-card-main { min-width: 0; }
.customer-tabs { display: flex; gap: 4px; padding: 0 14px; overflow-x: auto; border-bottom: 1px solid #e1ece4; }
.customer-tabs button { padding: 11px 12px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: #52665b; white-space: nowrap; font: inherit; cursor: pointer; }
.customer-tabs button[aria-pressed="true"] { color: #1f6d42; font-weight: 700; border-bottom-color: #2c9d58; }
.customer-tab-content, .side-panel { padding: 14px; }
.client-side, .next-card, .next-form { display: flex; flex-direction: column; gap: 9px; }
.client-note { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: 8px; margin-bottom: 14px; }
.customer-timeline, .related-list { padding: 0; margin: 0; list-style: none; }
.customer-timeline li { padding: 11px 0 11px 13px; border-left: 2px solid #dbecdf; overflow-wrap: anywhere; }
.customer-timeline li header { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px; }
.customer-timeline li p { margin: 5px 0 0; white-space: pre-wrap; }
.customer-timeline time, .client-empty, .related-list li span, .next-card span { color: #52665b; font-size: 12px; }
.side-panel h3, .sales-records h3 { font-size: 14px; margin: 0 0 8px; }
.side-panel .btn { margin-top: 8px; }
.sales-records { display: grid; gap: 8px; }
.related-list li { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 0; border-bottom: 1px solid #edf1ee; overflow-wrap: anywhere; }
.related-list li div > span { display: block; margin-top: 4px; }
.contact-actions { margin-bottom: 8px; }
@media (max-width: 680px) { .client-card-grid { grid-template-columns: 1fr; } .client-side { grid-row: 1; } }
</style>
