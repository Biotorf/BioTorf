<script setup>
import { computed, nextTick, ref, useId, watch } from 'vue';
import { useDbStore } from '@/stores/db';

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },
  label: { type: String, required: true },
  id: { type: String, default: '' },
  listKey: { type: String, default: '' },
  disabled: Boolean,
  searchable: Boolean,
  allowCreate: Boolean,
  hideLabel: Boolean,
  required: Boolean,
  placeholder: { type: String, default: '— не выбрано —' },
});
const emit = defineEmits(['update:modelValue', 'change', 'create-request', 'busy-change']);
const db = useDbStore();
const fallbackId = useId();
const controlId = computed(() => props.id || fallbackId);
const selectControl = ref(null);
const draftInput = ref(null);
const query = ref('');
const draft = ref('');
const adding = ref(false);
const saving = ref(false);
const error = ref('');
const selected = computed(() => String(props.modelValue ?? ''));
const canAdd = computed(() => props.listKey
  ? db.canAddListItem(props.listKey)
  : props.allowCreate);

watch(() => props.listKey, (key) => {
  if (key) db.refreshListOptions().catch(() => {});
}, { immediate: true });

const options = computed(() => {
  const byValue = new Map();
  for (const item of [...props.options, ...(db.data.lists?.[props.listKey] || [])]) {
    const value = item?.value ?? item;
    if ((typeof value !== 'string' && typeof value !== 'number') || value === '') continue;
    const key = String(value);
    if (!byValue.has(key)) byValue.set(key, { key, value, label: String(item?.label ?? value) });
  }
  if (selected.value && !byValue.has(selected.value)) {
    byValue.set(selected.value, { key: selected.value, value: props.modelValue, label: `${selected.value} (текущее)` });
  }
  return [...byValue.values()];
});

const showSearch = computed(() => props.searchable && options.value.length >= 10);
const filtered = computed(() => {
  const term = showSearch.value ? query.value.trim().toLocaleLowerCase('ru') : '';
  return term ? options.value.filter(({ key, label }) => key === selected.value ||
    label.toLocaleLowerCase('ru').includes(term) || key.toLocaleLowerCase('ru').includes(term)) : options.value;
});

function choose(value) {
  emit('update:modelValue', value);
  emit('change', value);
  query.value = '';
}

function onSelect(event) {
  choose(options.value.find(({ key }) => key === event.target.value)?.value ?? '');
}

async function toggleAdd() {
  if (!props.listKey) return emit('create-request');
  if (adding.value) return closeAdd();
  adding.value = true;
  await nextTick();
  draftInput.value?.focus();
}

function closeAdd() {
  adding.value = false;
  draft.value = '';
  error.value = '';
  selectControl.value?.focus();
}

async function saveOption() {
  const value = draft.value.trim();
  if (!value || props.disabled || saving.value) return;
  saving.value = true;
  error.value = '';
  emit('busy-change', true);
  try {
    choose(await db.addListItem(props.listKey, value));
    closeAdd();
  } catch (failure) {
    error.value = failure.message || 'Не удалось сохранить значение в общем справочнике.';
  } finally {
    saving.value = false;
    emit('busy-change', false);
    await nextTick();
    if (!adding.value) selectControl.value?.focus();
  }
}
</script>

<template>
  <div class="crm-select">
    <label v-if="!hideLabel" :for="controlId">{{ label }}</label>
    <input v-if="showSearch" v-model="query" class="input" type="search"
      :aria-label="`Поиск · ${label}`" placeholder="Поиск по списку" :disabled="disabled || saving"
      @keydown.enter.prevent="selectControl?.focus()" />
    <div class="control-row">
      <select :id="controlId" ref="selectControl" class="input select" :value="selected" :aria-label="label"
        :required="required" :disabled="disabled || saving" @change="onSelect">
        <option value="">{{ placeholder }}</option>
        <option v-for="option in filtered" :key="option.key" :value="option.key">{{ option.label }}</option>
      </select>
      <button v-if="canAdd" class="btn slim plus" type="button" :disabled="disabled || saving"
        :aria-label="`${listKey ? 'Добавить значение' : 'Создать запись'} · ${label}`"
        :aria-expanded="listKey ? adding : undefined" :title="listKey ? 'Добавить значение в справочник' : 'Создать связанную запись'"
        @click="toggleAdd">＋</button>
    </div>
    <div v-if="query.trim() && !filtered.some(({ key }) => key !== selected)" class="select-help" role="status">
      Нет совпадений
    </div>
    <div v-if="canAdd && adding" class="addition">
      <div class="control-row">
        <input ref="draftInput" v-model="draft" class="input" type="text" maxlength="500" placeholder="Новое значение"
          :aria-label="`Новое значение · ${label}`" :disabled="disabled || saving" @keydown.enter.prevent.stop="saveOption" />
        <button class="btn primary slim" type="button" :disabled="disabled || saving || !draft.trim()"
          @click="saveOption">{{ saving ? 'Сохранение…' : 'Добавить' }}</button>
        <button class="btn slim" type="button" :disabled="saving" :aria-label="`Отмена · ${label}`"
          @click="closeAdd">✕</button>
      </div>
      <div v-if="error" class="select-error" role="alert">{{ error }}</div>
    </div>
  </div>
</template>

<style scoped>
.crm-select { display: grid; gap: 5px; min-width: 0; }
.control-row { display: flex; gap: 5px; align-items: stretch; min-width: 0; }
.crm-select .input { min-width: 0; width: 100%; }
.control-row .input { flex: 1; }
.plus { flex: 0 0 34px; padding: 0; font-size: 16px; line-height: 1; border-radius: 8px; }
.addition { display: grid; gap: 5px; }
.addition .control-row { flex-wrap: wrap; }
.addition .input { min-width: 7rem; }
.select-help, .select-error { font-size: 12px; }
.select-help { color: var(--muted, #61756b); }
.select-error { color: #a42119; }
</style>
