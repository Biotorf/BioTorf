<script setup>
import { computed, ref } from 'vue';
import StatusPill from '@/components/ui/StatusPill.vue';
import { useFormatters } from '@/composables/useFormatters';
import { usePermissions } from '@/composables/usePermissions';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';

const props = defineProps({ leadId: { type: String, required: true } });
const db = useDbStore();
const ui = useUiStore();
const { day } = useFormatters();
const { canEditCollection } = usePermissions();
const lead = computed(() => db.leadById(props.leadId));
const client = computed(() => lead.value?.farmId ? db.farmById(lead.value.farmId) : null);
const journey = computed(() => db.journeys.find((row) => row.leadId === props.leadId));
const editor = ref(null);
const form = ref({});

function openWorkflow() {
  const route = journey.value || db.createJourneyFromLead(props.leadId);
  if (!route) return;
  ui.closeModal();
  ui.openJourney(route.id);
}

function edit() {
  const { name, contactName, phone, owner, source, next } = lead.value;
  form.value = { name, contactName, phone, owner, source, next };
  editor.value = 'lead';
}

function createTask() {
  form.value = { title: '', owner: lead.value.owner || ui.name || '', due: lead.value.next || '' };
  editor.value = 'task';
}

function save() {
  if (editor.value === 'lead') {
    if (!form.value.name.trim()) return;
    db.editEntity('lead', props.leadId, { ...form.value });
  } else {
    if (!form.value.title.trim()) return;
    db.addTask({ ...form.value, due: form.value.due || null, priority: 'Средний', refKind: 'lead', refId: props.leadId });
  }
  editor.value = null;
}
</script>

<template>
  <section v-if="lead" class="lead-card">
    <div class="client-hero">
      <div>
        <h3>{{ lead.name }}</h3>
        <div class="mini">{{ [lead.source, lead.date && day(lead.date)].filter(Boolean).join(' · ') }}</div>
      </div>
      <StatusPill :status="lead.status" />
    </div>

    <template v-if="!editor">
      <dl class="details-grid lead-details">
        <div class="detail">
          <dt>Клиент</dt>
          <dd><button v-if="client" type="button" class="lead-link" @click="ui.openClient(client.id)">{{ client.name }}</button><span v-else>Ещё не привязан</span></dd>
        </div>
        <div class="detail">
          <dt>Контакт</dt>
          <dd>{{ [lead.contactName, lead.phone].filter(Boolean).join(' · ') || '—' }}</dd>
        </div>
        <div class="detail"><dt>Ответственный</dt><dd>{{ lead.owner || '—' }}</dd></div>
        <div class="detail"><dt>Следующий контакт</dt><dd>{{ lead.next ? day(lead.next) : '—' }}</dd></div>
      </dl>

      <div class="actionbar lead-actions">
        <button v-if="journey || canEditCollection('journeys')" type="button" class="btn primary" @click="openWorkflow">
          {{ journey ? 'Открыть продажу' : 'Начать работу с заявкой' }}
        </button>
        <button v-if="canEditCollection('leads')" type="button" class="btn ghost" @click="edit">Редактировать</button>
        <button v-if="canEditCollection('tasks')" type="button" class="btn ghost" @click="createTask">Поставить задачу</button>
      </div>
    </template>

    <form v-else class="lead-form" @submit.prevent="save">
      <div v-if="editor === 'lead'" class="formgrid">
        <label class="field full">Тема заявки<input v-model.trim="form.name" class="input" required /></label>
        <label class="field">Контактное лицо<input v-model="form.contactName" class="input" /></label>
        <label class="field">Телефон<input v-model="form.phone" class="input" type="tel" /></label>
        <label class="field">Ответственный<input v-model="form.owner" class="input" /></label>
        <label class="field">Источник<input v-model="form.source" class="input" /></label>
        <label class="field">Дата следующего контакта<input v-model="form.next" class="input" type="date" /></label>
      </div>
      <div v-else class="formgrid">
        <label class="field full">Что нужно сделать<input v-model.trim="form.title" class="input" required /></label>
        <label class="field">Ответственный<input v-model="form.owner" class="input" /></label>
        <label class="field">Срок<input v-model="form.due" class="input" type="date" /></label>
      </div>
      <div class="actionbar lead-actions">
        <button type="submit" class="btn primary">Сохранить</button>
        <button type="button" class="btn ghost" @click="editor = null">Отмена</button>
      </div>
    </form>
  </section>
  <div v-else class="empty">Заявка не найдена.</div>
</template>

<style scoped>
.lead-details { margin: 14px 0; }
.lead-actions { margin-top: 14px; }
.lead-form { margin-top: 14px; }
.lead-link { border: 0; background: none; color: var(--green); padding: 0; font-weight: 650; text-align: left; }
.lead-link:hover { text-decoration: underline; }
</style>
