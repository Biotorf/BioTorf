<script setup>
// Рабочая карточка лида (руководство v0.9, §3 шаг 2): тема, источник, контакт,
// телефон, ответственный, статус, дата следующего действия + кнопки «Начать
// квалификацию», «Открыть сквозной процесс», «Создать задачу».
import { ref, computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';

const props = defineProps({ leadId: { type: String, required: true } });
const db = useDbStore();
const ui = useUiStore();
const { day } = useFormatters();

const lead = computed(() => db.data.leads.find((l) => l.id === props.leadId));
const farm = computed(() => lead.value?.farmId ? db.farmById(lead.value.farmId) : null);
const journey = computed(() => db.journeys.find((j) => j.leadId === props.leadId));

const editing = ref(false);
const form = ref({ name: '', phone: '', owner: '', source: '', next: '' });
function startEdit() {
  form.value = {
    name: lead.value?.name || '', phone: lead.value?.phone || '',
    owner: lead.value?.owner || '', source: lead.value?.source || '', next: lead.value?.next || '',
  };
  editing.value = true;
}
function saveEdit() {
  db.editEntity('lead', props.leadId, { ...form.value });
  editing.value = false;
}

function startQualification() {
  const j = journey.value || db.createJourneyFromLead(props.leadId);
  if (j) ui.openJourney(j.id);
}
function openJourneyView() {
  if (journey.value) ui.openJourney(journey.value.id);
  else startQualification();
}

const taskOpen = ref(false);
const task = ref({ title: '', owner: '', due: '' });
function createTask() {
  if (!task.value.title.trim()) return;
  db.addTask({
    title: task.value.title, owner: task.value.owner || lead.value?.owner || 'Менеджер А',
    due: task.value.due || lead.value?.next || null, priority: 'Средний',
    refKind: 'lead', refId: props.leadId, status: 'Открыта',
  });
  taskOpen.value = false;
  task.value = { title: '', owner: '', due: '' };
}
</script>

<template>
  <div v-if="lead">
    <div class="client-hero">
      <div>
        <div class="mini">ЛИД · {{ lead.id }}</div>
        <h3>{{ lead.name }}</h3>
        <div class="mini">Источник: {{ lead.source || '—' }} · Создан {{ day(lead.date) }}</div>
      </div>
      <StatusPill :status="lead.status" />
    </div>

    <div v-if="!editing" class="details-grid">
      <dl class="detail"><dt>Хозяйство</dt><dd>{{ farm ? farm.name : 'Не известно / создадим при квалификации' }}</dd></dl>
      <dl class="detail"><dt>Контакт / телефон</dt><dd>{{ lead.contactName || '—' }} {{ lead.phone || '' }}</dd></dl>
      <dl class="detail"><dt>Ответственный</dt><dd>{{ lead.owner }}</dd></dl>
      <dl class="detail"><dt>Следующий контакт</dt><dd>{{ day(lead.next) }}</dd></dl>
    </div>
    <div v-else class="muted-block">
      <div class="field"><label>Тема обращения</label><input v-model="form.name" class="input" /></div>
      <div class="field"><label>Телефон / WhatsApp</label><input v-model="form.phone" class="input" /></div>
      <div class="field"><label>Ответственный</label><input v-model="form.owner" class="input" /></div>
      <div class="field"><label>Источник</label><input v-model="form.source" class="input" /></div>
      <div class="field"><label>Следующий контакт</label><input v-model="form.next" type="date" class="input" /></div>
    </div>

    <div class="actionbar" style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
      <button v-if="!editing" class="btn ghost slim" @click="startEdit">Редактировать</button>
      <template v-else>
        <button class="btn primary slim" @click="saveEdit">Сохранить</button>
        <button class="btn ghost slim" @click="editing = false">Отмена</button>
      </template>
      <button class="btn primary slim" @click="startQualification">
        {{ journey ? 'Продолжить квалификацию' : 'Начать квалификацию' }}
      </button>
      <button v-if="journey" class="btn ghost slim" @click="openJourneyView">Открыть сквозной процесс</button>
      <button class="btn ghost slim" @click="taskOpen = !taskOpen">Создать задачу</button>
    </div>

    <div v-if="taskOpen" class="muted-block" style="margin-top:12px">
      <div class="field"><label>Задача (измеримый результат)</label><input v-model="task.title" class="input" placeholder="Напр.: созвониться и уточнить площадь" /></div>
      <div style="display:flex;gap:8px">
        <div class="field" style="flex:1"><label>Исполнитель</label><input v-model="task.owner" class="input" :placeholder="lead.owner" /></div>
        <div class="field" style="flex:1"><label>Срок</label><input v-model="task.due" type="date" class="input" /></div>
      </div>
      <button class="btn primary slim" :disabled="!task.title.trim()" @click="createTask">Добавить задачу</button>
    </div>

    <div v-if="journey" class="insight" style="margin-top:14px">
      <div><b>Маршрут {{ journey.id }}</b><div class="mini">Стадия: {{ journey.stage }} · следующий шаг {{ day(journey.next) }}</div></div>
      <button class="btn slim ghost" @click="openJourneyView">Перейти →</button>
    </div>

    <div class="actionbar" style="margin-top:16px">
      <button class="btn ghost slim" @click="ui.closeModal()">К списку</button>
    </div>
  </div>
  <div v-else class="empty">Лид не найден</div>
</template>
