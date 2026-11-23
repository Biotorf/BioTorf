<script setup>
// Единый редактор объектов (руководство v0.9 §5): «Редактировать» → поля →
// «Следующее действие» → «К списку». Охватывает основные сущности системы.
import { ref, computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { crmFieldLabel, REF_KINDS } from '@/data/crmFields';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';

const props = defineProps({ kind: { type: String, required: true }, id: { type: String, required: true } });
const db = useDbStore();
const ui = useUiStore();
const { canEditCollection } = usePermissions();

const TITLES = { task: 'Задача', deal: 'Сделка', lead: 'Лид', farm: 'Хозяйство', pilot: 'Пилот', order: 'Заказ', invoice: 'Счёт', shipment: 'Отгрузка', quote: 'КП' };
const rec = computed(() => {
  return (db.data[REF_KINDS[props.kind]] || []).find((x) => x.id === props.id);
});

const fields = computed(() => {
  if (!rec.value) return [];
  const types = { due: 'date', next: 'date', amount: 'number', area: 'number' };
  return ['name', 'title', 'number', 'stage', 'status', 'owner', 'due', 'next', 'amount', 'area', 'phone', 'priority']
    .filter((key) => key in rec.value && !(key === 'stage' && props.kind === 'deal' && rec.value.journeyId))
    .map((key) => [key, crmFieldLabel(REF_KINDS[props.kind], key), types[key]]);
});

const editing = ref(false);
const form = ref({});
function startEdit() {
  form.value = {};
  for (const [key] of fields.value) form.value[key] = rec.value?.[key] ?? '';
  editing.value = true;
}
function save() {
  db.editEntity(props.kind, props.id, { ...form.value });
  editing.value = false;
}
function createFollowUp() {
  ui.closeModal();
  ui.go('tasks', { new: '1', kind: props.kind, id: props.id, followUp: '1' });
}
function openRef() {
  const r = rec.value;
  if (!r) return;
  ui.closeModal();
  if (r.journeyId) ui.openJourney(r.journeyId);
  else if (r.farmId) ui.openClient(r.farmId);
}
</script>

<template>
  <div v-if="rec">
    <div class="client-hero">
      <div>
        <div class="mini">{{ TITLES[kind] }} · {{ id }}</div>
        <h3>{{ rec.title || rec.name || rec.number || id }}</h3>
      </div>
      <button v-if="(rec.farmId || rec.journeyId)" class="btn slim ghost" @click="openRef">Связанный объект →</button>
    </div>

    <div v-if="!editing" class="details-grid">
      <dl v-for="[key, label] in fields" :key="key" class="detail">
        <dt>{{ label }}</dt><dd>{{ rec[key] || '—' }}</dd>
      </dl>
    </div>
    <div v-else class="muted-block">
      <div v-for="[key, label, type] in fields" :key="key" class="field">
        <label>{{ label }}</label>
        <input v-model="form[key]" class="input" :type="type || 'text'" />
      </div>
    </div>

    <div class="actionbar" style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
      <button v-if="!editing" class="btn ghost slim" @click="startEdit">Редактировать</button>
      <template v-else>
        <button class="btn primary slim" @click="save">Сохранить</button>
        <button class="btn ghost slim" @click="editing = false">Отмена</button>
      </template>
      <button v-if="!editing && canEditCollection('tasks')" type="button" class="btn primary slim" @click="createFollowUp">Поставить задачу</button>
    </div>

    <div class="actionbar" style="margin-top:16px">
      <button class="btn ghost slim" @click="ui.closeModal()">К списку</button>
    </div>
  </div>
  <div v-else class="empty">Запись не найдена</div>
</template>
