<script setup>
// Единый редактор объектов (руководство v0.9 §5): «Редактировать» → поля →
// «Следующее действие» → «К списку». Охватывает основные сущности системы.
import { ref, computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';

const props = defineProps({ kind: { type: String, required: true }, id: { type: String, required: true } });
const db = useDbStore();
const ui = useUiStore();

const TITLES = { task: 'Задача', deal: 'Сделка', lead: 'Лид', farm: 'Хозяйство', pilot: 'Пилот', order: 'Заказ', invoice: 'Счёт', shipment: 'Отгрузка', quote: 'КП' };
const rec = computed(() => {
  const maps = { task: 'tasks', deal: 'deals', lead: 'leads', farm: 'farms', pilot: 'pilots', order: 'orders', invoice: 'invoices', shipment: 'shipments', quote: 'quotes' };
  return (db.data[maps[props.kind]] || []).find((x) => x.id === props.id);
});

const fields = computed(() => {
  if (!rec.value) return [];
  const r = rec.value;
  const common = [];
  if ('name' in r) common.push(['name', props.kind === 'lead' ? 'Тема обращения' : 'Название']);
  if ('title' in r) common.push(['title', 'Название']);
  if ('number' in r) common.push(['number', 'Номер документа']);
  if ('stage' in r) common.push(['stage', 'Стадия']);
  if ('status' in r) common.push(['status', 'Статус']);
  if ('owner' in r) common.push(['owner', 'Ответственный']);
  if ('due' in r) common.push(['due', 'Срок', 'date']);
  if ('next' in r) common.push(['next', 'Следующий контакт', 'date']);
  if ('amount' in r) common.push(['amount', 'Сумма, сом', 'number']);
  if ('area' in r) common.push(['area', 'Площадь, га', 'number']);
  if ('phone' in r) common.push(['phone', 'Телефон']);
  if ('priority' in r) common.push(['priority', 'Приоритет']);
  return common;
});

const editing = ref(false);
const form = ref({});
function startEdit() {
  form.value = {};
  for (const [key] of fields.value) form.value[key] = rec.value?.[key] ?? '';
  editing.value = true;
}
const nextAction = ref({ result: '', owner: '', due: '' });

function save() {
  db.editEntity(props.kind, props.id, { ...form.value });
  editing.value = false;
}
function applyNext() {
  if (!nextAction.value.result.trim()) return;
  db.addTask({
    title: nextAction.value.result, owner: nextAction.value.owner || rec.value?.owner || 'Менеджер А',
    due: nextAction.value.due || null, priority: 'Средний',
    refKind: props.kind, refId: props.id, status: 'Открыта',
  });
  if (rec.value && 'next' in rec.value && nextAction.value.due) rec.value.next = nextAction.value.due;
  db.save('Следующее действие', `${TITLES[props.kind]} ${props.id}`);
  nextAction.value = { result: '', owner: '', due: '' };
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
    </div>

    <div class="muted-block" style="margin-top:12px">
      <b class="mini">СЛЕДУЮЩЕЕ ДЕЙСТВИЕ</b>
      <div class="field"><label>Результат (что нужно сделать)</label><input v-model="nextAction.result" class="input" placeholder="Напр.: отправить КП по картофелю" /></div>
      <div style="display:flex;gap:8px">
        <div class="field" style="flex:1"><label>Исполнитель</label><input v-model="nextAction.owner" class="input" :placeholder="rec.owner || ''" /></div>
        <div class="field" style="flex:1"><label>Срок</label><input v-model="nextAction.due" type="date" class="input" /></div>
      </div>
      <button class="btn primary slim" :disabled="!nextAction.result.trim()" @click="applyNext">Поставить задачу</button>
    </div>

    <div class="actionbar" style="margin-top:16px">
      <button class="btn ghost slim" @click="ui.closeModal()">К списку</button>
    </div>
  </div>
  <div v-else class="empty">Запись не найдена</div>
</template>
