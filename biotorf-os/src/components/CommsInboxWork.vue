<script setup>
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { commsApi } from '@/api/commsClient';
import { INBOX_STATES, isResponseOverdue } from '@/data/commsInbox';

const props = defineProps({
  chat: { type: Object, required: true },
  staff: { type: Object, required: true },
});
const emit = defineEmits(['updated', 'client-saved']);
const db = useDbStore();
const ui = useUiStore();
const { canEdit, canEditCollection, canSeeFarm } = usePermissions();
const work = computed(() => props.chat.work);
const editable = computed(() => canEdit('comms') &&
  (props.staff.canAssignOthers || !work.value.assignee || work.value.assignee === props.staff.login));
const canLinkLead = computed(() => canEditCollection('leads'));
const inbound = computed(() => props.chat.messages?.some((message) => message.dir === 'in'));

const editing = ref(false);
const form = ref(null);
const busy = ref(false);
const error = ref('');
const revised = computed(() => !!form.value && form.value.revision !== work.value.revision);
const owner = computed(() => props.staff.items.find((person) => person.login === work.value.assignee));
const dueText = computed(() => work.value.responseDue
  ? new Date(work.value.responseDue).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
  : '');
const clientTypes = ['Частный покупатель', 'Компания', 'Агропроизводитель', 'Розничный магазин',
  'Оптовая база', 'Дилер', 'Дистрибьютор', 'Другой'];
const clientDraft = ref(null);
const clientMode = ref('new');
const clientMatches = ref([]);
const clientQuery = ref('');
const linkedClient = ref(null);
const savedClient = ref(null);
const clientOptions = computed(() => {
  const matches = new Map(clientMatches.value.map((row) => [row.id, row]));
  if (linkedClient.value) return [linkedClient.value];
  const options = [...matches.values(), ...db.farms.filter(canSeeFarm).filter((row) => !matches.has(row.id))];
  const query = clientQuery.value.trim().toLowerCase();
  return options.filter((row) => row.id === clientDraft.value?.clientId ||
    !query || [row.name, row.phone, row.id].some((value) => String(value || '').toLowerCase().includes(query)));
});
const defaultAssignee = computed(() => clientDraft.value?.assignee || work.value.assignee || props.staff.login);

function localDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return new Date(date.valueOf() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function startEdit() {
  clientDraft.value = null;
  form.value = { ...work.value, responseDue: localDate(work.value.responseDue) };
  error.value = '';
  editing.value = true;
}
async function openClientForm() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  savedClient.value = null;
  try {
    const data = await commsApi.clientContext(props.chat.key);
    editing.value = false;
    clientQuery.value = '';
    linkedClient.value = data.linkedClient;
    clientMatches.value = data.matches || [];
    clientMode.value = linkedClient.value || clientMatches.value.length ? 'existing' : 'new';
    clientDraft.value = {
      revision: data.revision,
      source: data.source,
      clientId: linkedClient.value?.id || (clientMatches.value.length === 1 ? clientMatches.value[0].id : ''),
      name: data.name || '', type: '', phone: data.phone || '', contactName: data.contactName || '',
      assignee: work.value.assignee || props.staff.login || '',
    };
  } catch (err) { error.value = err.message; }
  finally { busy.value = false; }
}
async function saveClient() {
  if (busy.value || !clientDraft.value) return;
  busy.value = true;
  error.value = '';
  try {
    const { source, ...fields } = clientDraft.value;
    const result = await commsApi.saveClient(props.chat.key, {
      ...fields, clientId: clientMode.value === 'existing' ? fields.clientId : null,
    });
    clientDraft.value = null;
    savedClient.value = result.client;
    emit('client-saved', props.chat.key, result);
  } catch (err) {
    error.value = err.message;
    if (err.detail?.matches?.length) {
      clientMatches.value = err.detail.matches;
      clientDraft.value.clientId = clientMatches.value.length === 1 ? clientMatches.value[0].id : '';
      clientMode.value = 'existing';
    }
  } finally { busy.value = false; }
}
async function save() {
  if (busy.value || revised.value) return;
  busy.value = true;
  error.value = '';
  try {
    const values = {
      ...form.value,
      responseDue: form.value.responseDue ? new Date(form.value.responseDue).toISOString() : null,
      assignee: form.value.assignee || null,
      leadId: form.value.leadId || null,
    };
    emit('updated', props.chat.key, await commsApi.updateWork(props.chat.key, values));
    editing.value = false;
  } catch (err) { error.value = err.message; }
  finally { busy.value = false; }
}
async function openLead(id) {
  if (!(db.leads || []).some((lead) => lead.id === id)) await db.pullCrmState();
  if ((db.leads || []).some((lead) => lead.id === id)) ui.openLeadCard(id);
  else error.value = 'Связанный лид не найден. Проверьте привязку диалога.';
}
async function createLead() {
  busy.value = true;
  error.value = '';
  try {
    const result = await commsApi.createLead(props.chat.key, work.value.revision);
    emit('updated', props.chat.key, result.work);
    await openLead(result.lead.id);
  } catch (err) { error.value = err.message; }
  finally { busy.value = false; }
}
</script>

<template>
  <div class="inbox-work">
    <div class="work-line">
      <strong>{{ INBOX_STATES[work.state] }}</strong>
      <span>{{ owner?.name || work.assignee || 'Без ответственного' }}</span>
      <span v-if="dueText" :class="{ 'work-error': isResponseOverdue(work) }">Ответ до {{ dueText }}</span>
      <button v-if="chat.farmId" type="button" class="btn slim ghost" @click="ui.openClient(chat.farmId)">Карточка клиента</button>
      <button v-else-if="editable && canEditCollection('farms') && !clientDraft" type="button" class="btn slim primary"
              :disabled="busy" @click="openClientForm">＋ Сохранить клиента</button>
      <button v-if="work.leadId" type="button" class="btn slim ghost" @click="openLead(work.leadId)">Открыть лид</button>
      <button v-else-if="editable && canLinkLead && inbound" type="button" class="btn slim ghost" :disabled="busy"
              @click="createLead">Создать лид</button>
      <button v-if="editable && !editing && !clientDraft" type="button" class="btn slim ghost" @click="startEdit">Ведение диалога</button>
    </div>
    <form v-if="clientDraft" class="client-capture" @submit.prevent="saveClient">
      <header>
        <strong>Клиент из диалога</strong>
        <span v-if="clientDraft.source" class="mini">Источник · {{ clientDraft.source }}</span>
      </header>
      <div class="work-line" role="group" aria-label="Способ сохранения клиента">
        <button v-if="!linkedClient" type="button" class="btn slim" :class="{ primary: clientMode === 'new' }" :aria-pressed="clientMode === 'new'"
                @click="clientMode = 'new'">Новый клиент</button>
        <button type="button" class="btn slim" :class="{ primary: clientMode === 'existing' }" :aria-pressed="clientMode === 'existing'"
                @click="clientMode = 'existing'">Связать с существующим</button>
      </div>
      <p v-if="linkedClient" class="mini">Клиент уже указан в связанной продаже. Привяжите к нему переписку.</p>
      <p v-else-if="clientMatches.length && clientMode === 'existing'" class="mini">
        Найдены карточки с таким телефоном или Telegram.
      </p>
      <div class="capture-fields">
        <template v-if="clientMode === 'new'">
          <label>Имя или название<input v-model="clientDraft.name" class="input" required maxlength="200" /></label>
          <label>Тип клиента<select v-model="clientDraft.type" class="select">
            <option value="">Выбрать позже</option>
            <option v-for="kind in clientTypes" :key="kind">{{ kind }}</option>
          </select></label>
          <label>Контактное лицо<input v-model="clientDraft.contactName" class="input" maxlength="200" /></label>
          <label>Телефон<input v-model="clientDraft.phone" type="tel" class="input" maxlength="60" /></label>
        </template>
        <template v-else>
          <label v-if="!linkedClient">Найти клиента<input v-model="clientQuery" type="search" class="input" placeholder="Имя, компания, телефон" /></label>
          <label>Клиент<select v-model="clientDraft.clientId" class="select" required>
            <option value="">Выберите клиента</option>
            <option v-for="row in clientOptions" :key="row.id" :value="row.id">{{ row.name }}</option>
          </select></label>
          <button v-if="!linkedClient" class="btn slim ghost" type="button" @click="db.pullCrmState()">Обновить список клиентов</button>
        </template>
        <label v-if="staff.canAssignOthers">Ответственный<select v-model="clientDraft.assignee" class="select">
          <option v-if="defaultAssignee && !staff.items.some(({ login }) => login === defaultAssignee)" :value="defaultAssignee">
            {{ defaultAssignee }}
          </option>
          <option v-for="person in staff.items" :key="person.login" :value="person.login">{{ person.name }}</option>
        </select></label>
      </div>
      <div class="work-line">
        <button type="submit" class="btn slim primary" :disabled="busy || (clientMode === 'new' ? !clientDraft.name.trim() : !clientDraft.clientId)">
          {{ clientMode === 'new' ? 'Создать и привязать' : 'Привязать диалог' }}
        </button>
        <button type="button" class="btn slim ghost" :disabled="busy" @click="clientDraft = null; error = ''">Отмена</button>
      </div>
    </form>
    <p v-if="savedClient" class="mini client-saved" role="status">Диалог связан с клиентом «{{ savedClient.name }}».</p>
    <form v-if="editing" class="work-form" @submit.prevent="save">
      <label>Статус<select v-model="form.state" class="select">
        <option v-for="(name, state) in INBOX_STATES" :key="state" :value="state">{{ name }}</option>
      </select></label>
      <label>Ответственный<select v-model="form.assignee" class="select">
        <option :value="null">Без ответственного</option>
        <option v-if="form.assignee && !staff.items.some((person) => person.login === form.assignee)"
                :value="form.assignee">{{ form.assignee }}</option>
        <option v-for="person in staff.items" :key="person.login" :value="person.login">{{ person.name }}</option>
      </select></label>
      <label>Ответить до<input v-model="form.responseDue" type="datetime-local" class="input" /></label>
      <label v-if="canLinkLead">Связанный лид<select v-model="form.leadId" class="select">
        <option :value="null">Без привязки</option>
        <option v-if="form.leadId && !(db.leads || []).some((lead) => lead.id === form.leadId)" :value="form.leadId">
          {{ form.leadId }}
        </option>
        <option v-for="lead in db.leads" :key="lead.id" :value="lead.id">{{ lead.name || lead.id }}</option>
      </select></label>
      <button type="submit" class="btn primary slim" :disabled="busy || revised">Сохранить</button>
      <button type="button" class="btn ghost slim" @click="editing = false">Свернуть</button>
      <button v-if="revised" type="button" class="btn ghost slim" @click="startEdit">Загрузить изменения</button>
    </form>
    <p v-if="error || revised && editing" class="mini work-error" role="alert">
      {{ error || 'Диалог обновил коллега. Загрузите изменения.' }}
    </p>
  </div>
</template>

<style scoped>
.inbox-work { padding: 8px 16px; background: #fff; border-top: 1px solid #e7ece8; }
.work-line, .work-form { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; }
.work-line { font-size: 12px; }
.work-form { margin-top: 8px; align-items: end; }
.work-form label { display: grid; gap: 3px; font-size: 12px; max-width: min(100%, 200px); min-width: 8rem; }
.work-error { color: #b42318; margin-bottom: 0; }
.client-capture { display: grid; gap: 8px; margin-top: 7px; padding: 10px; border: 1px solid #e0e9e5; border-radius: 10px; background: #f8faf9; }
.client-capture header { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.client-capture p, .client-saved { margin: 0; }
.capture-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(135px, 100%), 1fr)); gap: 6px 9px; align-items: end; }
.capture-fields label { display: grid; gap: 3px; font-size: 12px; min-width: 0; }
.client-saved { padding-top: 4px; color: #22684d; }
</style>
