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
const emit = defineEmits(['updated']);
const db = useDbStore();
const ui = useUiStore();
const { canEdit, canEditCollection } = usePermissions();
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

function localDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return new Date(date.valueOf() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function startEdit() {
  form.value = { ...work.value, responseDue: localDate(work.value.responseDue) };
  error.value = '';
  editing.value = true;
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
      <button v-if="work.leadId" type="button" class="btn slim ghost" @click="openLead(work.leadId)">Открыть лид</button>
      <button v-else-if="editable && canLinkLead && inbound" type="button" class="btn slim ghost" :disabled="busy"
              @click="createLead">Создать лид</button>
      <button v-if="editable && !editing" type="button" class="btn slim ghost" @click="startEdit">Ведение диалога</button>
    </div>
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
</style>
