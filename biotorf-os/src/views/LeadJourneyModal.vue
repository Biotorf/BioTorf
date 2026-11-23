<script setup>
import { computed, ref } from 'vue';
import CrmSelectField from '@/components/CrmSelectField.vue';
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
  ui.closeModal();
  ui.go('tasks', { new: '1', lead: props.leadId });
}

function save() {
  if (!form.value.name.trim()) return;
  db.editEntity('lead', props.leadId, { ...form.value });
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
      <div class="formgrid">
        <label class="field full">Тема заявки<input v-model.trim="form.name" class="input" required /></label>
        <label class="field">Контактное лицо<input v-model="form.contactName" class="input" /></label>
        <label class="field">Телефон<input v-model="form.phone" class="input" type="tel" /></label>
        <CrmSelectField v-model="form.owner" label="Ответственный" :options="db.optionsFor('owners', 'leads', 'owner')" list-key="owners" />
        <CrmSelectField v-model="form.source" label="Источник" :options="db.optionsFor('sources', 'leads', 'source')" list-key="sources" />
        <label class="field">Дата следующего контакта<input v-model="form.next" class="input" type="date" /></label>
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
