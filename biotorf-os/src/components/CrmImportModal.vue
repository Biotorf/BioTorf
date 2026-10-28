<script setup>
// Универсальная модалка наполнения таблицы CRM: загрузка CSV/JSON-файла,
// предпросмотр первых строк, режимы «Добавить/обновить» (merge) и
// «Заменить всё» (replace), а также полная очистка таблицы.
import { ref, computed } from 'vue';
import { useDbStore } from '@/stores/db';

const props = defineProps({
  coll: { type: String, required: true },   // коллекция db.js: farms, leads, deals…
  title: { type: String, default: 'Импорт данных' },
});
const emit = defineEmits(['close']);

const db = useDbStore();
const fileInput = ref(null);
const records = ref([]);
const fileName = ref('');
const mode = ref('merge');
const busy = ref(false);
const error = ref('');
const done = ref('');

const preview = computed(() => records.value.slice(0, 5));
const columns = computed(() => {
  const keys = new Set();
  for (const r of records.value.slice(0, 50)) Object.keys(r).forEach((k) => keys.add(k));
  return [...keys];
});

async function onFile(e) {
  error.value = ''; done.value = '';
  const f = e.target.files?.[0];
  if (!f) return;
  fileName.value = f.name;
  try {
    const text = await f.text();
    if (/\.json$/i.test(f.name) || text.trim().startsWith('[')) {
      const parsed = JSON.parse(text);
      if (!Array.isArray(parsed)) throw new Error('JSON должен быть массивом объектов');
      records.value = parsed.filter((r) => r && typeof r === 'object');
    } else {
      records.value = db.csvToRecords(text);
    }
    if (!records.value.length) error.value = 'В файле нет ни одной строки с данными';
  } catch (err) {
    error.value = 'Не удалось прочитать файл: ' + err.message;
    records.value = [];
  }
}

async function apply() {
  if (!records.value.length) return;
  busy.value = true; error.value = ''; done.value = '';
  try {
    const res = await db.importCollection(props.coll, records.value, mode.value);
    done.value = `Загружено: создано ${res.created ?? 0}, обновлено ${res.updated ?? 0}.`
      + (mode.value === 'replace' ? ' Старые записи заменены.' : '');
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function wipe() {
  if (!confirm(`Удалить ВСЕ записи из таблицы «${props.coll}»? Действие необратимо.`)) return;
  busy.value = true; error.value = ''; done.value = '';
  try {
    const res = await db.wipeCollection(props.coll);
    done.value = `Таблица очищена (удалено ${res.removed}).`;
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <header>
        <h3>{{ title }}: {{ coll }}</h3>
        <button class="x" @click="emit('close')">✕</button>
      </header>

      <div class="row">
        <input ref="fileInput" type="file" accept=".csv,.txt,.json" @change="onFile" />
      </div>
      <p v-if="fileName" class="hint">Файл: {{ fileName }} — строк: {{ records.length }}</p>
      <p v-else class="hint">Поддерживаются CSV (разделитель , или ;) и JSON (массив объектов). Первая строка CSV — заголовки полей.</p>

      <div v-if="preview.length" class="table-wrap">
        <table class="preview">
          <thead><tr><th v-for="c in columns" :key="c">{{ c }}</th></tr></thead>
          <tbody><tr v-for="(r, i) in preview" :key="i"><td v-for="c in columns" :key="c">{{ r[c] }}</td></tr></tbody>
        </table>
        <p v-if="records.length > preview.length" class="hint">…и ещё {{ records.length - preview.length }} строк</p>
      </div>

      <div class="row modes">
        <label><input type="radio" value="merge" v-model="mode" /> Добавить / обновить по id</label>
        <label><input type="radio" value="replace" v-model="mode" /> Заменить всю таблицу</label>
      </div>

      <p v-if="error" class="err">{{ error }}</p>
      <p v-if="done" class="ok">{{ done }}</p>

      <footer>
        <button class="ghost danger" :disabled="busy" @click="wipe">Очистить таблицу</button>
        <span class="spacer" />
        <button class="ghost" :disabled="busy" @click="emit('close')">Закрыть</button>
        <button class="primary" :disabled="busy || !records.length" @click="apply">
          {{ busy ? 'Загрузка…' : 'Загрузить' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay { position: fixed; inset: 0; background: rgba(15, 23, 18, .45); display: flex; align-items: center; justify-content: center; z-index: 60; }
/* непрозрачное окно — контент страницы не просвечивает */
.modal { width: min(720px, 92vw); max-height: 84vh; overflow: auto; background: #ffffff; color: #1c2b21; border-radius: 14px; padding: 18px 20px; box-shadow: 0 18px 48px rgba(0,0,0,.28); }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
h3 { margin: 0; font-size: 16px; }
.x { border: 0; background: none; font-size: 16px; cursor: pointer; color: #667; }
.row { margin: 8px 0; }
.hint { font-size: 12px; color: #5a6a5e; }
.table-wrap { overflow-x: auto; border: 1px solid #dfe7df; border-radius: 10px; margin: 8px 0; }
table.preview { border-collapse: collapse; width: 100%; font-size: 12px; }
table.preview th, table.preview td { border-bottom: 1px solid #e6ece6; padding: 5px 8px; text-align: left; white-space: nowrap; max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
table.preview th { background: #f2f6f2; }
.modes label { margin-right: 16px; font-size: 13px; }
.err { color: #b3261e; font-size: 13px; }
.ok { color: #1d7a3e; font-size: 13px; }
footer { display: flex; gap: 8px; align-items: center; margin-top: 12px; }
.spacer { flex: 1; }
button { border-radius: 9px; padding: 8px 14px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
button:disabled { opacity: .55; cursor: default; }
.primary { background: #1d7a3e; color: #fff; }
.ghost { background: #fff; border-color: #cfd8cf; color: #2a3a2e; }
.ghost.danger { color: #b3261e; border-color: #ecc9c6; }
</style>
