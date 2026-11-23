<script setup>
import { ref } from 'vue';

const props = defineProps({
  exercise: { type: Object, required: true },
});
const emit = defineEmits(['solved']);

const selected = ref(null);
const solved = ref(false);
const message = ref('');
const name = ref('');
const type = ref('');
const region = ref('');

function choose(index) {
  if (solved.value) return;
  selected.value = index;
  solved.value = index === props.exercise.answer;
  message.value = solved.value ? props.exercise.success : props.exercise.retry;
  if (solved.value) emit('solved');
}

function saveClient() {
  if (name.value.trim().toLocaleLowerCase('ru') !== 'магазин сад') {
    message.value = 'В учебном задании клиент называется «Магазин Сад».';
  } else if (type.value !== 'Розничный магазин') {
    message.value = 'Для магазина выберите тип «Розничный магазин».';
  } else if (region.value !== 'Чуйская область') {
    message.value = 'Выберите «Чуйская область», как в задании.';
  } else {
    solved.value = true;
    message.value = 'Готово. Теперь попробуйте создать настоящую карточку в разделе «Клиенты», когда она понадобится.';
    emit('solved');
  }
}
</script>

<template>
  <div class="exercise">
    <p class="exercise-prompt">{{ exercise.prompt }}</p>
    <div v-if="exercise.kind === 'choice'" class="exercise-choices" role="group" aria-label="Варианты ответа">
      <button v-for="(option, index) in exercise.options" :key="option" type="button" class="exercise-option"
        :class="{ correct: selected === index && solved, retry: selected === index && !solved }"
        :aria-pressed="selected === index" :aria-disabled="solved" @click="choose(index)">
        <span class="exercise-letter" aria-hidden="true">{{ ['А', 'Б', 'В', 'Г'][index] }}</span>
        {{ option }}
      </button>
    </div>
    <form v-else class="exercise-client" @submit.prevent="saveClient">
      <fieldset :disabled="solved">
        <label class="exercise-name">Имя или название <input v-model="name" required class="input" autocomplete="off" /></label>
        <label>Тип клиента
          <select v-model="type" class="select" required>
            <option value="">Выберите тип</option>
            <option>Частный покупатель</option>
            <option>Розничный магазин</option>
            <option>Агропроизводитель</option>
          </select>
        </label>
        <label>Регион
          <select v-model="region" class="select" required>
            <option value="">Выберите регион</option>
            <option>Бишкек</option>
            <option>Ошская область</option>
            <option>Чуйская область</option>
          </select>
        </label>
        <button type="submit" class="btn">Сохранить учебную карточку</button>
      </fieldset>
    </form>
    <p v-if="message" class="exercise-feedback" :class="solved ? 'correct' : 'retry'" role="status">{{ message }}</p>
  </div>
</template>

<style scoped>
.exercise { display: grid; gap: 12px; }
.exercise p { margin: 0; }
.exercise-prompt { font-weight: 600; line-height: 1.5; }
.exercise-choices { display: grid; gap: 7px; }
.exercise-option { display: flex; align-items: center; gap: 8px; padding: 8px 10px; text-align: start; color: var(--ink); background: var(--surface-soft, var(--bg)); border: 1px solid var(--border); border-radius: 10px; font: inherit; cursor: pointer; }
.exercise-option:hover:not([aria-disabled="true"]) { border-color: var(--green); }
.exercise-option[aria-disabled="true"] { cursor: default; }
.exercise-letter { display: grid; place-items: center; width: 26px; height: 26px; flex: 0 0 auto; background: var(--panel); border: 1px solid var(--border); color: var(--green); border-radius: 6px; font-size: 12px; font-weight: 750; }
.exercise-client fieldset { min-width: 0; display: grid; gap: 8px; grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 12px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-soft, var(--bg)); }
.exercise-client label { display: grid; gap: 4px; min-width: 0; font-size: 12px; font-weight: 650; }
.exercise-client .input, .exercise-client .select { width: 100%; min-width: 0; }
.exercise-name, .exercise-client button { grid-column: 1 / -1; justify-self: stretch; }
.exercise-feedback { padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; font-size: 13px; }
.correct { background: var(--accent-soft, var(--mint)); border-color: var(--green); color: var(--accent-ink, var(--green)); }
.retry { background: var(--danger-soft, #fcece7); border-color: var(--danger-ink, #ae4335); color: var(--danger-ink, #ae4335); }
@media (max-width: 350px) { .exercise-client fieldset { grid-template-columns: minmax(0, 1fr); } }
</style>
