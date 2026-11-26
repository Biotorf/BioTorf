<script setup>
import { computed, onMounted, ref } from 'vue';
import { organizationApi } from '@/api/organizationClient';
import RequisiteFields from '@/components/forms/RequisiteFields.vue';
import { useUiStore } from '@/stores/ui';

const ui = useUiStore();
const canManage = computed(() => ['director', 'operations'].includes(ui.role));
const draft = ref(null);
const working = ref(false);
const error = ref('');
const status = ref('');

async function load() {
  working.value = true;
  error.value = '';
  status.value = '';
  try {
    draft.value = await organizationApi.get();
  } catch (err) {
    error.value = err.message;
  } finally {
    working.value = false;
  }
}

async function save() {
  if (!canManage.value || working.value) return;
  working.value = true;
  error.value = '';
  status.value = '';
  try {
    draft.value = await organizationApi.save(draft.value);
    status.value = 'Реквизиты сохранены.';
  } catch (err) {
    error.value = err.message;
  } finally {
    working.value = false;
  }
}

onMounted(() => { if (canManage.value) load(); });
</script>

<template>
  <section>
    <header class="pagehead">
      <div>
        <h1>Настройки организации</h1>
        <p class="subtitle">Реквизиты нашей компании для печатных документов</p>
      </div>
    </header>
    <p v-if="!canManage">Раздел доступен директору и операционному руководителю.</p>
    <form v-else class="panel" @submit.prevent="save">
      <p v-if="error" class="danger-text" role="alert">{{ error }}</p>
      <p v-if="status" role="status">{{ status }}</p>
      <p v-if="working && !draft" role="status">Загружаем реквизиты…</p>
      <fieldset v-if="draft" :disabled="working">
        <legend>Реквизиты организации</legend>
        <RequisiteFields :values="draft" contacts @update="(key, value) => draft[key] = value" />
      </fieldset>
      <div class="actionbar">
        <button v-if="error" type="button" class="btn" :disabled="working" @click="load">Загрузить с сервера</button>
        <button v-if="draft" class="btn primary" :disabled="working">Сохранить реквизиты</button>
      </div>
    </form>
  </section>
</template>
