<script setup>
import { computed } from 'vue';
import { COMPANY_CONTACT_FIELDS, REQUISITE_FIELDS } from '@/data/requisites';

const props = defineProps({
  values: { type: Object, required: true },
  contacts: Boolean,
});
const emit = defineEmits(['update']);
const fields = computed(() => props.contacts ? [...REQUISITE_FIELDS, ...COMPANY_CONTACT_FIELDS] : REQUISITE_FIELDS);
</script>

<template>
  <div class="requisite-fields">
    <label v-for="[key, label] in fields" :key="key" class="field">
      {{ label }}
      <input :value="values[key] ?? ''" class="input" :type="key === 'email' ? 'email' : 'text'"
        :maxlength="key === 'address' || key.endsWith('Address') ? 500 : 250"
        @input="emit('update', key, $event.target.value)" />
    </label>
  </div>
</template>

<style scoped>
.requisite-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 14px; margin-block: 12px; }
</style>
