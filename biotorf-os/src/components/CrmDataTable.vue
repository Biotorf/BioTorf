<script setup>
import { computed, nextTick, ref, watch } from 'vue';
import { isLate, useDbStore } from '@/stores/db';
import { crmFields, crmFieldLabel, crmValue, crmDisplayValue, crmTitle, crmDictionaryKey, REF_FIELD, REF_KINDS, LOGISTICS_KINDS } from '@/data/crmFields';
import { usePermissions } from '@/composables/usePermissions';
import StatusPill from '@/components/ui/StatusPill.vue';

const props = defineProps({
  coll: { type: String, required: true },
  rows: { type: Array, required: true },
  columns: { type: Array, default: null },
  empty: { type: String, default: 'Записей нет.' },
});
const db = useDbStore();
const { canEditCollection } = usePermissions();
const fields = computed(() => props.columns || crmFields(props.coll, props.rows));
const dictionaryColumns = computed(() => {
  if (!canEditCollection(props.coll)) return {};
  return Object.fromEntries(fields.value.map((field) => [field, crmDictionaryKey(props.coll, field)])
    .filter(([, key]) => key && db.canAddListItem(key)));
});
const addition = ref(null);
const draft = ref('');
const input = ref(null);
const savingOption = ref(false);
const optionError = ref('');
const optionStatus = ref('');
watch(() => props.coll, () => {
  addition.value = null;
  optionStatus.value = '';
});

async function openAddition(field, event) {
  addition.value = { field, dictionary: dictionaryColumns.value[field], button: event.currentTarget };
  draft.value = '';
  optionError.value = '';
  optionStatus.value = '';
  await nextTick();
  input.value?.focus({ preventScroll: true });
  input.value?.scrollIntoView({ block: 'nearest' });
}

function closeAddition() {
  const button = addition.value?.button;
  addition.value = null;
  button?.focus();
}

async function saveOption() {
  const entry = addition.value;
  const label = draft.value.trim();
  if (!entry || !label || savingOption.value) return;
  savingOption.value = true;
  optionError.value = '';
  try {
    const value = await db.addListItem(entry.dictionary, label);
    if (addition.value === entry) {
      optionStatus.value = `«${value}» теперь доступно в списке «${crmFieldLabel(props.coll, entry.field)}».`;
      closeAddition();
    }
  } catch (error) {
    optionError.value = error.message || 'Не удалось сохранить значение в справочнике.';
  } finally {
    savingOption.value = false;
  }
}

function display(row, key) {
  const value = crmValue(props.coll, row, key);
  if (props.coll === 'logistics' && key === 'kind' && LOGISTICS_KINDS[value]) return LOGISTICS_KINDS[value];
  const target = REF_FIELD[key] || (key === 'refId' ? REF_KINDS[row.refKind] : null);
  const linked = target && db.data[target]?.find((item) => String(item.id) === String(value));
  if (linked) return crmTitle(linked) + ' · ' + linked.id;
  return crmDisplayValue(value);
}
</script>

<template>
  <div>
    <form v-if="addition" class="dictionary-addition" @submit.prevent="saveOption" @keydown.esc.stop.prevent="!savingOption && closeAddition()">
      <label>{{ crmFieldLabel(coll, addition.field) }}
        <input v-model="draft" ref="input" class="input" type="text" maxlength="500" required :disabled="savingOption"
          :aria-label="`Новое значение · ${crmFieldLabel(coll, addition.field)}`" placeholder="Новое значение" />
      </label>
      <button class="btn primary slim" type="submit" :disabled="savingOption || !draft.trim()">{{ savingOption ? 'Сохраняем…' : 'Добавить' }}</button>
      <button class="btn ghost slim" type="button" :disabled="savingOption" @click="closeAddition">Отмена</button>
      <p v-if="optionError" class="danger-text" role="alert">{{ optionError }}</p>
    </form>
    <p v-if="optionStatus" class="dictionary-status mini" role="status">{{ optionStatus }}</p>
    <div class="table-wrap crm-table-scroll" tabindex="0" aria-label="Таблица записей">
      <table class="table">
        <thead>
          <tr>
            <th v-if="$slots.actions" scope="col">Действия</th>
            <th v-for="key in fields" :key="key" scope="col">
              {{ crmFieldLabel(coll, key) }}
              <button v-if="dictionaryColumns[key]" class="btn slim dictionary-plus" type="button"
                :aria-label="`Добавить значение · ${crmFieldLabel(coll, key)}`" :aria-expanded="addition?.field === key"
                :disabled="savingOption" @click="openAddition(key, $event)">＋</button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td v-if="$slots.actions"><div class="row-actions"><slot name="actions" :row="row" /></div></td>
            <td v-for="key in fields" :key="key">
              <slot :name="key" :row="row" :value="display(row, key)">
                <StatusPill v-if="key === 'status' && row.status" :status="row.status" />
                <ul v-else-if="key === 'items' && Array.isArray(row.items) && row.items.length" class="items">
                  <li v-for="(item, index) in row.items" :key="index">
                    <template v-if="item && typeof item === 'object'">
                      <span v-for="([field, value]) in Object.entries(item).filter(([field]) => field !== 'qty' || item.packs == null)" :key="field">
                        <b>{{ crmFieldLabel(coll, field) }}</b> {{ crmDisplayValue(value) }}
                      </span>
                    </template>
                    <span v-else>{{ crmDisplayValue(item) }}</span>
                  </li>
                </ul>
                <span v-else class="field-value" :class="{ 'danger-text': key === 'due' && isLate(row.due) &&
                  ((coll === 'invoices' && !row.paid) || (coll === 'tasks' && !['Выполнена', 'Отменена'].includes(row.status))) }">{{ display(row, key) }}</span>
              </slot>
            </td>
          </tr>
          <tr v-if="!rows.length"><td :colspan="fields.length + ($slots.actions ? 1 : 0)" class="empty">{{ empty }}</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.crm-table-scroll { max-width: 100%; overflow: auto; }
th { white-space: nowrap; }
.dictionary-plus { margin-inline-start: 3px; padding: 0 4px; min-height: 24px; line-height: 1; }
.dictionary-addition { display: flex; align-items: end; gap: 8px; flex-wrap: wrap; margin: 0 0 10px; }
.dictionary-addition label { display: grid; gap: 4px; }
.dictionary-addition p { flex-basis: 100%; margin: 0; }
.dictionary-status { margin: 0 0 8px; }
.field-value { display: block; width: max-content; max-width: 28rem; white-space: pre-wrap; overflow-wrap: anywhere; }
.row-actions { display: flex; gap: 4px; flex-wrap: wrap; min-width: 7rem; }
.items { margin: 0; padding-inline-start: 1.25rem; min-width: 13rem; }
.items span { display: block; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
