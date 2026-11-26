<script setup>
import { REQUISITE_FIELDS } from '@/data/requisites';
import { computed, nextTick, ref, watch } from 'vue';
import { checkApi, commsApi } from '@/api/commsClient';
import { clientInitials, clientRecords, phoneDigits, primaryContact as findPrimaryContact } from '@/data/clientDesk';
import { useDbStore, isLate } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import { crmPhotoLink } from '@/utils/crmPhotoLink';
import { crmTitle, crmValue, REF_KINDS } from '@/data/crmFields';
import CrmRowModal from '@/components/CrmRowModal.vue';
import CrmSelectField from '@/components/CrmSelectField.vue';
import CrmPhotoGallery from '@/components/photos/CrmPhotoGallery.vue';
import CrmPhotoThumbnail from '@/components/photos/CrmPhotoThumbnail.vue';
import StatusPill from '@/components/ui/StatusPill.vue';

const props = defineProps({
  farmId: { type: String, required: true },
  embedded: { type: Boolean, default: false },
});
const db = useDbStore();
const ui = useUiStore();
const { canEditCollection, canSeeFarm } = usePermissions();
const { day } = useFormatters();
const moneyFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });
const money = (amount) => moneyFormat.format(Number(amount) || 0) + ' сом';

const farm = computed(() => {
  const entry = db.farmById(props.farmId);
  return entry && canSeeFarm(entry) ? entry : null;
});
function shownDate(value) {
  if (!value) return '—';
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return day(value);
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString('ru-RU', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

const related = computed(() => farm.value ? clientRecords(db.data, props.farmId) : {});
const contacts = computed(() => related.value.contacts || []);
const primaryContact = computed(() => findPrimaryContact(contacts.value));
const phone = computed(() => farm.value?.phone || primaryContact.value?.phone);
const email = computed(() => farm.value?.email || primaryContact.value?.email);
const tasks = computed(() => (db.data.tasks || []).filter((task) => {
  if (task.refKind === 'farm') return String(task.refId) === props.farmId;
  return related.value[REF_KINDS[task.refKind]]?.some(({ id }) => String(id) === String(task.refId));
}));
const openTasks = computed(() => tasks.value
  .filter((task) => !/^(выполнена|отменена|закрыта)$/i.test(task.status || ''))
  .sort((a, b) => String(a.due || '9999').localeCompare(String(b.due || '9999'))));
const nextAction = computed(() => openTasks.value[0]);
const profileFields = computed(() => [
  ['Тип клиента', farm.value?.type],
  ['Регион', farm.value?.region],
  ['Ответственный', farm.value?.owner],
  ['Источник', farm.value?.source],

  ['Культура', farm.value?.crop],
  ['Площадь', farm.value?.area != null && farm.value.area !== '' ? farm.value.area + ' га' : ''],
].filter(([, value]) => value != null && value !== ''));
const inactiveDeals = /^(завершена?|закрыта?|отмен[её]н[ао]?|проиграна?|отказ|выиграна?|успешно реализовано|оплачено|доставка|получено клиентом|сопровождение)$/i;
const activeDeals = computed(() => (related.value.deals || []).filter((row) => !inactiveDeals.test(crmValue('deals', row, 'stage') || row.status || '')));
const pipelineAmount = computed(() => activeDeals.value
  .map((deal) => deal.amount != null && deal.amount !== '' ? Number(deal.amount) : NaN)
  .filter(Number.isFinite)
  .reduce((sum, amount) => (sum ?? 0) + amount, null));
function invoiceBalance(invoice) {
  return db.invoiceBalance({ ...invoice, paid: invoice.paid === true || invoice.paid === 1 ||
    /^(true|1|да|yes)$/i.test(String(invoice.paid)) });
}
const financial = computed(() => (related.value.invoices || [])
  .filter((invoice) => !/^отмен[её]н[ао]?$/i.test(invoice.status || ''))
  .reduce((totals, invoice) => {
    const balance = invoiceBalance(invoice);
    const amount = Math.max(0, Number(invoice.amount) || 0);
    totals.issued += amount;
    totals.outstanding += balance;
    if (balance > 0) totals.open += 1;
    return totals;
  }, { issued: 0, outstanding: 0, open: 0 }));
const salesGroups = [
  ['leads', 'Обращения'], ['deals', 'Сделки'], ['quotes', 'Предложения'],
  ['orders', 'Заказы'], ['shipments', 'Отгрузки'], ['pilots', 'Пилоты'],
];
const financeGroups = [['invoices', 'Счета'], ['payments', 'Платежи']];
const journeys = computed(() => related.value.journeys || []);
const salesCount = computed(() => salesGroups.reduce((total, [table]) => total + (related.value[table]?.length || 0), journeys.value.length));
const financeCount = computed(() => financeGroups.reduce((total, [table]) => total + (related.value[table]?.length || 0), 0));
const tabs = computed(() => [
  { id: 'overview', label: 'Обзор' }, { id: 'photos', label: 'Фото' }, { id: 'history', label: 'История' },
  { id: 'sales', label: 'Продажи', count: salesCount.value },
  { id: 'finance', label: 'Финансы', count: financeCount.value },
  { id: 'contacts', label: 'Контакты', count: contacts.value.length },
  { id: 'requisites', label: 'Реквизиты' },
  { id: 'docs', label: 'Документы', count: related.value.clientDocs?.length },
]);
const active = ref('overview');
const photoCoverId = ref();
function setPhotoCover(cover) { photoCoverId.value = cover?.id ?? ''; }
watch(() => props.farmId, () => { photoCoverId.value = undefined; });
const historyKind = ref('all');
const historyLimit = ref(30);
const historyPageSize = 50;
const remoteMessages = ref([]);
const remoteTotal = ref(0);
const remoteOffset = ref(0);
const historyLoaded = ref(false);
const commsLoading = ref(false);
const historyError = ref('');
const comms = computed(() => {
  const items = new Map(remoteMessages.value.map((message) => [message.id, message]));
  for (const message of db.data.comms || []) {
    if (String(message.farmId) === props.farmId && (!historyLoaded.value || String(message.id).startsWith('C-local-'))) {
      items.set(message.id, message);
    }
  }
  return [...items.values()];
});
async function loadHistory(append = false) {
  if (commsLoading.value || !farm.value) return;
  commsLoading.value = true;
  historyError.value = '';
  try {
    if (!(await checkApi())) return;
    const offset = append ? remoteOffset.value : 0;
    const { items, total } = await commsApi.list({ farmId: props.farmId, limit: historyPageSize, offset });
    const merged = new Map((append ? remoteMessages.value : []).map((message) => [message.id, message]));
    for (const message of items) merged.set(message.id, message);
    remoteMessages.value = [...merged.values()];
    remoteTotal.value = total;
    remoteOffset.value = offset + items.length;
    historyLoaded.value = true;
  } catch {
    historyError.value = 'Не удалось обновить историю переписки.';
  } finally {
    commsLoading.value = false;
  }
}
watch(() => farm.value?.id, () => { if (farm.value) loadHistory(); }, { immediate: true });
watch(historyKind, () => { historyLimit.value = 30; });
const noteText = ref('');
const noteInput = ref(null);
const planning = ref(false);
const action = ref({ title: '', due: '', owner: '' });
const starting = ref(false);
const cardError = ref('');
const edit = ref(null);

const channelNames = { call: 'Звонок', telegram: 'Telegram', whatsapp: 'WhatsApp', email: 'Почта' };
const timeline = computed(() => {
  const entries = [];
  const messageNoteIds = new Set(comms.value.map((message) => 'hist:' + message.id));
  for (const item of comms.value) {
    const direction = item.dir === 'in' ? 'входящий' : 'исходящий';
    entries.push({
      id: 'comm:' + item.id, date: item.ts, kind: 'comms',
      title: (channelNames[item.kind] || item.kind || 'Связь') + ' · ' + direction,
      text: [item.text, item.note].filter(Boolean).join('\n') || item.status || item.contact || '',
    });
  }
  for (const item of related.value.clientNotes || []) {
    if (messageNoteIds.has(item.id)) continue;
    entries.push({ id: 'note:' + item.id, date: item.ts || item.date, kind: 'notes', title: 'Заметка', text: item.text });
  }
  for (const item of tasks.value) {
    entries.push({
      id: 'task:' + item.id, date: item.createdAt || item.due, kind: 'tasks',
      title: 'Задача · ' + item.title,
      text: [item.owner, item.status, item.due && 'до ' + day(item.due)].filter(Boolean).join(' · '),
    });
  }
  for (const [table, title] of [['deals', 'Сделка'], ['orders', 'Заказ'], ['invoices', 'Счёт'], ['shipments', 'Отгрузка']]) {
    for (const record of related.value[table] || []) {
      entries.push({
        id: table + ':' + record.id, date: record.date || record.createdAt, kind: 'sales',
        title: title + ' · ' + crmTitle(record), text: record.stage || record.status,
        href: recordUrl(table, record.id),
      });
    }
  }
  return entries.sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
});
const shownHistory = computed(() => timeline.value.filter((row) => historyKind.value === 'all' || row.kind === historyKind.value));
const lastCommunication = computed(() => comms.value.reduce((latest, message) =>
  String(message.ts || '').localeCompare(latest) > 0 ? String(message.ts) : latest, ''));
function addNote() {
  active.value = 'history';
  historyKind.value = 'all';
  nextTick(() => noteInput.value?.focus());
}
function contactHandles(contact) {
  const telegram = String(contact.telegram || '').trim().replace(/^@/, '');
  const whatsapp = phoneDigits(contact.whatsapp);
  return {
    telegram: /^[A-Za-z0-9_]{5,32}$/.test(telegram) ? 'https://t.me/' + telegram : '',
    whatsapp: whatsapp.length >= 8 ? 'https://wa.me/' + whatsapp : '',
  };
}
function recordSummary(table, record) {
  const state = table === 'deals' ? crmValue(table, record, 'stage') : record.status || record.stage;
  const date = record.date || record.planDate || record.createdAt;
  const amount = record.amount ?? record.total;
  return [
    state, amount != null && amount !== '' ? money(amount) : '',
    table === 'invoices' && invoiceBalance(record) > 0 ? 'к оплате ' + money(invoiceBalance(record)) : '',
    date ? shownDate(date) : '',
  ].filter(Boolean).join(' · ');
}

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
      <div class="summary-identity">
        <button type="button" class="identity-icon" aria-label="Открыть фотографии клиента" @click="active = 'photos'">
          <CrmPhotoThumbnail collection="farms" :record-id="String(farm.id)" :cover-id="photoCoverId">
            <template #fallback>{{ clientInitials(farm.name) }}</template>
          </CrmPhotoThumbnail>
        </button>
        <div>
          <div v-if="farm.type || farm.region" class="client-type">{{ [farm.type, farm.region].filter(Boolean).join(' · ') }}</div>
          <component :is="embedded ? 'h1' : 'h2'">{{ farm.name || farm.id }}</component>
          <div class="client-meta">
            <StatusPill v-if="farm.status" :status="farm.status" />
            <a v-if="phone" :href="'tel:' + phone">{{ phone }}</a>
            <a v-if="email" :href="'mailto:' + email">{{ email }}</a>
          </div>
        </div>
      </div>
      <div class="client-actions">
        <button class="btn" @click="openComms">Переписка и звонки</button>
        <button v-if="canEditCollection('farms')" class="btn ghost" @click="edit = { coll: 'farms', record: farm }">Изменить</button>
        <button v-if="canEditCollection('leads')" class="btn primary" :disabled="starting" @click="startSale">{{ starting ? 'Открываем…' : 'Новая продажа' }}</button>
      </div>
    </header>
    <p v-if="cardError" class="danger-text" role="alert">{{ cardError }}</p>
    <CrmRowModal v-if="edit" :key="`${edit.coll}:${edit.record?.id || 'new'}:${!!edit.requisitesOnly}`" inline :requisites-only="edit.requisitesOnly" :coll="edit.coll" :record="edit.record" :initial-values="edit.initial" @close="edit = null" />

    <dl class="account-metrics" aria-label="Показатели клиента">
      <div><dt>Активные сделки</dt><dd>{{ activeDeals.length }}<small v-if="pipelineAmount != null">{{ money(pipelineAmount) }}</small></dd></div>
      <div><dt>Заказы</dt><dd>{{ related.orders?.length || 0 }}</dd></div>
      <div><dt>К оплате по счетам</dt><dd :class="{ 'has-balance': financial.outstanding > 0 }">{{ money(financial.outstanding) }}</dd></div>
      <div><dt>Последняя связь</dt><dd>{{ shownDate(lastCommunication) }}</dd></div>
    </dl>

    <div class="client-card-grid">
      <section class="client-card-main panel">
        <nav class="customer-tabs" aria-label="Разделы карточки">
          <button v-for="tab in tabs" :key="tab.id" type="button" :aria-pressed="active === tab.id"
            :data-tour="tab.id === 'photos' ? 'client-photos' : undefined" @click="active = tab.id">
            {{ tab.label }}<span v-if="tab.count" class="tab-count">{{ tab.count }}</span>
          </button>
        </nav>
        <div v-if="active === 'overview'" class="customer-tab-content">
          <div class="section-heading">
            <h3>О клиенте</h3>
            <button v-if="canEditCollection('clientNotes')" class="btn slim" @click="addNote">Добавить заметку</button>
          </div>
          <dl v-if="profileFields.length" class="profile-fields">
            <div v-for="[label, value] in profileFields" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></div>
          </dl>
          <p v-else class="client-empty">Профиль клиента пока не заполнен.</p>
          <p v-if="crmValue('farms', farm, 'notes')" class="profile-notes">{{ crmValue('farms', farm, 'notes') }}</p>
          <div class="section-heading recent-heading">
            <h3>Недавние события</h3>
            <button class="inline-link" @click="active = 'history'">Вся история</button>
          </div>
          <ul v-if="timeline.length" class="related-list compact-activity">
            <li v-for="entry in timeline.slice(0, 5)" :key="entry.id">
              <div><a v-if="entry.href" :href="entry.href">{{ entry.title }}</a><strong v-else>{{ entry.title }}</strong><span v-if="entry.text">{{ entry.text }}</span></div>
              <time v-if="entry.date" :datetime="entry.date">{{ shownDate(entry.date) }}</time>
            </li>
          </ul>
          <p v-else class="client-empty">Событий пока нет.</p>
        </div>

        <div v-else-if="active === 'requisites'" class="customer-tab-content">
          <div class="section-heading">
            <h3>Реквизиты для документов</h3>
            <button v-if="canEditCollection('farms')" class="btn slim"
              @click="edit = { coll: 'farms', record: farm, requisitesOnly: true }">Изменить реквизиты</button>
          </div>
          <dl class="profile-fields">
            <div v-for="[label, value] in REQUISITE_FIELDS.map(([key, label]) => [label, farm[key]])" :key="label">
              <dt>{{ label }}</dt><dd>{{ value || '—' }}</dd>
            </div>
          </dl>
        </div>

        <div v-else-if="active === 'photos'" class="customer-tab-content">
          <CrmPhotoGallery collection="farms" :record-id="String(farm.id)" :record-name="farm.name"
            :editable="canEditCollection('farms')" @loaded="setPhotoCover" @changed="setPhotoCover" />
        </div>

        <div v-else-if="active === 'history'" class="customer-tab-content">
          <div class="section-heading">
            <label class="field history-select">Показать
              <select v-model="historyKind" class="select">
                <option value="all">Все события</option>
                <option value="comms">Переписка и звонки</option>
                <option value="notes">Заметки</option>
                <option value="tasks">Задачи</option>
                <option value="sales">Продажи</option>
              </select>
            </label>
            <button type="button" class="btn slim" :disabled="commsLoading" @click="loadHistory()">{{ commsLoading ? 'Загружаем…' : 'Обновить переписку' }}</button>
          </div>
          <p v-if="historyError" class="client-empty" role="status">{{ historyError }}</p>
          <form v-if="canEditCollection('clientNotes') && ['all', 'notes'].includes(historyKind)" class="client-note" @submit.prevent="saveNote">
            <label class="field">Заметка
              <textarea ref="noteInput" v-model="noteText" class="input" rows="2" placeholder="Что обсудили с клиентом?" />
            </label>
            <button class="btn slim" :disabled="!noteText.trim()">Добавить</button>
          </form>
          <ul v-if="shownHistory.length" class="customer-timeline">
            <li v-for="entry in shownHistory.slice(0, historyLimit)" :key="entry.id" :data-kind="entry.kind">
              <header>
                <a v-if="entry.href" :href="entry.href">{{ entry.title }}</a><strong v-else>{{ entry.title }}</strong>
                <time v-if="entry.date" :datetime="entry.date">{{ shownDate(entry.date) }}</time>
              </header>
              <p v-if="entry.text">{{ entry.text }}</p>
            </li>
          </ul>
          <p v-else class="client-empty">По этому фильтру событий пока нет.</p>
          <div class="client-actions history-actions">
            <button v-if="shownHistory.length > historyLimit" class="btn slim" @click="historyLimit += 30">Показать ещё события</button>
            <button v-if="['all', 'comms'].includes(historyKind) && remoteOffset < remoteTotal && remoteOffset > 0"
              class="btn slim" :disabled="commsLoading" @click="loadHistory(true); historyLimit += historyPageSize">Загрузить раннюю переписку</button>
          </div>
        </div>

        <div v-else-if="active === 'sales' || active === 'finance' || active === 'docs'" class="customer-tab-content sales-records">
          <template v-if="active === 'finance'">
            <dl class="finance-totals">
              <div><dt>Выставлено</dt><dd>{{ money(financial.issued) }}</dd></div>
              <div><dt>Учтено оплат</dt><dd>{{ money(financial.issued - financial.outstanding) }}</dd></div>
              <div><dt>Счета к оплате</dt><dd>{{ financial.open }}</dd></div>
            </dl>
          </template>
          <div v-if="active === 'sales' && journeys.length">
            <h3>Процессы продажи</h3>
            <ul class="related-list">
              <li v-for="record in journeys" :key="record.id">
                <div><strong>{{ db.leadById(record.leadId)?.name || record.id }}</strong><span>{{ record.stage }}</span></div>
                <button class="btn slim" @click="openJourney(record.id)">Открыть</button>
              </li>
            </ul>
          </div>
          <div v-if="active === 'docs' && canEditCollection('clientDocs')" class="contact-actions">
            <button class="btn slim" @click="edit = { coll: 'clientDocs', initial: { farmId: farm.id } }">Добавить документ</button>
          </div>
          <div v-for="[table, title] in active === 'sales' ? salesGroups : active === 'finance' ? financeGroups : [['clientDocs', 'Документы клиента'], ['logistics', 'Документы логистики']]" :key="table">
            <template v-if="related[table]?.length">
              <h3>{{ title }}</h3>
              <ul class="related-list">
                <li v-for="record in related[table]" :key="record.id">
                  <div><strong>{{ crmTitle(record) }}</strong><span v-if="recordSummary(table, record)">{{ recordSummary(table, record) }}</span></div>
                  <a class="btn slim" :href="recordUrl(table, record.id)" @click="!embedded && ui.closeModal()">Открыть</a>
                </li>
              </ul>
            </template>
          </div>
          <p v-if="active === 'sales' && !salesCount" class="client-empty">Продаж пока нет. Новую продажу можно начать вверху карточки.</p>
          <p v-if="active === 'finance' && !financeCount" class="client-empty">Счетов и платежей пока нет.</p>
          <p v-if="active === 'docs' && !related.clientDocs?.length && !related.logistics?.length" class="client-empty">Документов пока нет.</p>
        </div>

        <div v-else class="customer-tab-content">
          <div v-if="canEditCollection('contacts')" class="contact-actions">
            <button class="btn slim" @click="edit = { coll: 'contacts', initial: { farmId: farm.id } }">＋ Контакт</button>
          </div>
          <ul v-if="contacts.length" class="related-list">
            <li v-for="contact in contacts" :key="contact.id">
              <div>
                <strong>{{ contact.name || contact.id }}<span v-if="contact.id === primaryContact?.id"> · основной</span></strong>
                <span v-if="contact.role">{{ contact.role }}</span>
                <div class="contact-links">
                  <a v-if="contact.phone" :href="'tel:' + contact.phone">{{ contact.phone }}</a>
                  <a v-if="contact.email" :href="'mailto:' + contact.email">{{ contact.email }}</a>
                  <a v-if="contactHandles(contact).telegram" :href="contactHandles(contact).telegram" target="_blank" rel="noopener">Telegram</a>
                  <a v-if="contactHandles(contact).whatsapp" :href="contactHandles(contact).whatsapp" target="_blank" rel="noopener">WhatsApp</a>
                  <a :href="crmPhotoLink('contacts', contact.id)" @click="!embedded && ui.closeModal()">Фото</a>
                </div>
              </div>
              <button v-if="canEditCollection('contacts')" class="btn slim" @click="edit = { coll: 'contacts', record: contact }">Изменить</button>
            </li>
          </ul>
          <p v-else class="client-empty">Дополнительных контактов пока нет.</p>
        </div>
      </section>

      <aside class="client-side">
        <section class="panel side-panel next-panel">
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
            <CrmSelectField v-model="action.owner" label="Ответственный" :options="db.optionsFor('owners', 'tasks', 'owner')" list-key="owners" />
            <label class="field">Срок <input v-model="action.due" class="input" type="date" /></label>
            <div class="client-actions">
              <button type="button" class="btn slim" @click="planning = false">Отмена</button>
              <button class="btn primary slim" :disabled="!action.title.trim()">Сохранить</button>
            </div>
          </form>
        </section>
        <section v-if="primaryContact || phone || email" class="panel side-panel">
          <h3>Связь с клиентом</h3>
          <div class="next-card">
            <strong v-if="primaryContact?.name">{{ primaryContact.name }}</strong>
            <span v-if="primaryContact?.role">{{ primaryContact.role }}</span>
            <a v-if="phone" :href="'tel:' + phone">{{ phone }}</a>
            <a v-if="email" :href="'mailto:' + email">{{ email }}</a>
          </div>
        </section>
      </aside>
    </div>
    <Teleport to="body">
    </Teleport>
  </article>
  <p v-else class="empty">Карточка клиента недоступна.</p>
</template>

<style scoped>
.client-summary { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; background: #f1f8f3; border: 1px solid #d7e9dc; border-radius: 14px; padding: 18px; margin-bottom: 14px; }
.summary-identity { display: flex; min-width: 0; align-items: center; gap: 14px; }
.identity-icon { display: grid; place-items: center; flex: 0 0 48px; inline-size: 48px; aspect-ratio: 1; padding: 0; border: 0; border-radius: 13px; overflow: hidden; background: var(--accent-soft, #dcefe4); color: var(--accent-ink, #216c4c); font-weight: 800; font-size: 18px; cursor: pointer; }
.account-metrics, .finance-totals { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; margin: 0 0 12px; }
.account-metrics > div, .finance-totals > div { background: #fff; border: 1px solid #e1ece4; border-radius: 11px; padding: 10px 12px; min-width: 0; }
.account-metrics dt, .finance-totals dt, .profile-fields dt { color: #52665b; font-size: 12px; }
.account-metrics dd, .finance-totals dd, .profile-fields dd { margin: 4px 0 0; font-weight: 700; overflow-wrap: anywhere; }
.account-metrics dd { font-size: clamp(14px, 2vw, 18px); }
.account-metrics dd small { display: block; color: #52665b; font-size: 12px; font-weight: 550; }
.has-balance { color: #97531e; }
.finance-totals { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.tab-count { margin-inline-start: 5px; color: #527266; font-size: 11px; }
.section-heading { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 10px; }
.section-heading h3 { margin: 0; font-size: 15px; }
.profile-fields { margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 155px), 1fr)); gap: 10px; }
.profile-fields > div { border-bottom: 1px solid #edf1ee; padding: 4px 0 7px; }
.profile-notes { margin: 12px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.recent-heading { margin-top: 18px; }
.inline-link { border: 0; color: #216c4c; background: transparent; font: inherit; font-weight: 650; text-align: start; }
.compact-activity li div { min-width: 0; }
.compact-activity li div > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.compact-activity time { font-size: 12px; color: #52665b; flex: none; }
.history-select { font-size: 12px; color: #52665b; }
.history-select .select { min-width: 150px; }
.history-actions { margin-top: 12px; }
.contact-links { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 5px; }
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
.customer-timeline li[data-kind="comms"] { border-left-color: #8dbbb1; }
.customer-timeline li[data-kind="tasks"] { border-left-color: #e2bd82; }
.customer-timeline li[data-kind="sales"] { border-left-color: #9faada; }
.customer-timeline li header { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px; }
.customer-timeline li p { margin: 5px 0 0; white-space: pre-wrap; }
.customer-timeline time, .client-empty, .related-list li span, .next-card span { color: #52665b; font-size: 12px; }
.side-panel h3, .sales-records h3 { font-size: 14px; margin: 0 0 8px; }
.side-panel .btn { margin-top: 8px; }
.sales-records { display: grid; gap: 8px; }
.related-list li { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 0; border-bottom: 1px solid #edf1ee; overflow-wrap: anywhere; }
.related-list li div > span { display: block; margin-top: 4px; }
.contact-actions { margin-bottom: 8px; }

@media (max-width: 680px) {
  .client-card-grid { grid-template-columns: 1fr; }
  .client-side { grid-row: 1; }
  .account-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .client-summary { padding: 14px; }
  .compact-activity li { flex-wrap: wrap; }
}
</style>
