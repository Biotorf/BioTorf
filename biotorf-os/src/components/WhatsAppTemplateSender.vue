<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { commsApi } from '@/api/commsClient';

const props = defineProps({
  phone: { type: String, default: '' },
  contact: { type: String, default: '' },
});
const emit = defineEmits(['result']);
const templates = ref([]);
const selection = ref('');
const chosen = computed(() => templates.value.find((entry) => templateKey(entry) === selection.value));
const values = ref([]);
const loading = ref(true);
const busy = ref(false);
const error = ref('');

const templateKey = (entry) => entry.name + '/' + entry.language;
watch(chosen, (entry) => { values.value = (entry?.parameters || []).map(() => ''); });
onMounted(async () => {
  try {
    templates.value = (await commsApi.whatsappTemplates()).items || [];
    if (templates.value.length === 1) selection.value = templateKey(templates.value[0]);
  } catch (err) {
    error.value = err.message || 'Не удалось загрузить шаблоны WhatsApp.';
  } finally {
    loading.value = false;
  }
});

async function sendTemplate() {
  if (!chosen.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const result = await commsApi.sendWhatsAppTemplate({
      phone: props.phone.trim(), contact: props.contact.trim() || null,
      name: chosen.value.name, language: chosen.value.language,
      parameters: values.value.map((value) => value.trim()),
    });
    if (result.error) error.value = result.error;
    emit('result', result);
  } catch (err) {
    error.value = err.message || 'Не удалось отправить шаблон.';
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <fieldset class="template-sender">
    <legend>Одобренный шаблон WhatsApp</legend>
    <p v-if="loading" class="mini" role="status">Загружаем шаблоны…</p>
    <p v-else-if="!templates.length && !error" class="mini">В настройках сервера пока нет разрешённых шаблонов WhatsApp.</p>
    <template v-if="templates.length">
      <label>Шаблон
        <select v-model="selection" class="select">
          <option value="">Выберите шаблон</option>
          <option v-for="entry in templates" :key="templateKey(entry)" :value="templateKey(entry)">
            {{ entry.label }} · {{ entry.language }}
          </option>
        </select>
      </label>
      <label v-for="(label, index) in chosen?.parameters || []" :key="index">{{ label }}
        <input v-model="values[index]" class="input" maxlength="1024" />
      </label>
      <button class="btn primary slim" type="button"
              :disabled="!chosen || !phone.trim() || values.some((value) => !value.trim()) || busy"
              @click="sendTemplate">{{ busy ? 'Отправляем…' : 'Отправить шаблон' }}</button>
    </template>
    <p v-if="error" class="danger-text" role="alert">{{ error }}</p>
  </fieldset>
</template>

<style scoped>
.template-sender { display: grid; min-width: 0; gap: 8px; padding: 8px; border: 1px solid var(--line, #dce5df); border-radius: 8px; }
.template-sender label { display: grid; gap: 4px; }
.template-sender p { margin: 0; }
</style>
