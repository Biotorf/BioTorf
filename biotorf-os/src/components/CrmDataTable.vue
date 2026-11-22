<script setup>
import { computed } from 'vue';
import { isLate, useDbStore } from '@/stores/db';
import { crmFields, crmFieldLabel, crmValue, crmDisplayValue, crmTitle, REF_FIELD, REF_KINDS, LOGISTICS_KINDS } from '@/data/crmFields';
import StatusPill from '@/components/ui/StatusPill.vue';

const props = defineProps({
  coll: { type: String, required: true },
  rows: { type: Array, required: true },
  columns: { type: Array, default: null },
  empty: { type: String, default: 'Записей нет.' },
});
const db = useDbStore();
const fields = computed(() => props.columns || crmFields(props.coll, props.rows));

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
  <div class="table-wrap crm-table-scroll" tabindex="0" aria-label="Таблица записей">
    <table class="table">
      <thead>
        <tr>
          <th v-if="$slots.actions" scope="col">Действия</th>
          <th v-for="key in fields" :key="key" scope="col">{{ crmFieldLabel(coll, key) }}</th>
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
</template>

<style scoped>
.crm-table-scroll { max-width: 100%; overflow: auto; }
th { white-space: nowrap; }
.field-value { display: block; width: max-content; max-width: 28rem; white-space: pre-wrap; overflow-wrap: anywhere; }
.row-actions { display: flex; gap: 4px; flex-wrap: wrap; min-width: 7rem; }
.items { margin: 0; padding-inline-start: 1.25rem; min-width: 13rem; }
.items span { display: block; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
