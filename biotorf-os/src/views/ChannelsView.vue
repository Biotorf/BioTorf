<script setup>
// «Каналы CRM» — подключение мессенджеров и площадок из настроек приложения.
// Больше не нужно править farms.json/.env: добавляем канал, вставляем токен/секрет,
// входящие сообщения приходят через generic-вебхук POST /webhooks/channel/{kind}.
import { ref, computed, onMounted } from 'vue';
import { channelsApi } from '../api/channelsClient';
import { apiState } from '../api/commsClient';

const items = ref([]);
const presets = ref([]);
const loading = ref(false);
const error = ref('');
const okMsg = ref('');

// модалка подключения аккаунта
const connectFor = ref(null);          // канал, для которого открываем форму
const form = ref({ login: '', displayName: '', token: '', secret: '' });
const busy = ref(false);

// форма добавления своего канала
const showAdd = ref(false);
const newCh = ref({ kind: '', label: '', icon: '🔗', group: 'Прочее' });

// раскрывающийся список вебхука
const hookOpen = ref(null);
const origin = typeof window !== 'undefined' ? window.location.origin : '';

const TOKEN_HINTS = {
  telegram: 'Токен бота из @BotFather (1234567:AA…)',
  whatsapp: 'Token WhatsApp Business Cloud API (EAAG…)',
  call: 'Секрет вебхука вашей АТС (приходит в заголовке X-Webhook-Secret)',
  default: 'Токен/ключ доступа (не виден никому, хранится в базе сервера)',
};
const SECRET_LABELS = {
  telegram: 'Не обязателен',
  default: 'Секрет вебхука (X-Webhook-Secret)',
};

async function load() {
  loading.value = true; error.value = '';
  try {
    const res = await channelsApi.list();
    items.value = res.items || [];
    presets.value = res.presets || [];
  } catch (e) {
    error.value = String(e.message || e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const availablePresets = computed(() =>
  presets.value.filter((p) => !items.value.some((c) => c.id === p.id)));

function openConnect(ch) {
  connectFor.value = ch;
  form.value = { login: '', displayName: '', token: '', secret: '' };
  okMsg.value = '';
}
function closeConnect() { connectFor.value = null; }

async function doConnect() {
  const ch = connectFor.value;
  busy.value = true; error.value = '';
  try {
    await channelsApi.connect(ch.id, { ...form.value });
    okMsg.value = `Аккаунт ${ch.label} подключён`;
    connectFor.value = null;
    await load();
  } catch (e) {
    error.value = e.status422?.detail || String(e.message || e);
  } finally { busy.value = false; }
}

async function toggleChannel(ch) {
  error.value = '';
  try {
    await channelsApi.patch(ch.id, { enabled: !ch.enabled });
    await load();
  } catch (e) { error.value = String(e.message || e); }
}

async function removeAccount(ch, acc) {
  if (!confirm(`Отключить аккаунт «${acc.displayName || acc.login || ch.label}»?`)) return;
  error.value = '';
  try {
    await channelsApi.removeAccount(acc.id);
    await load();
  } catch (e) { error.value = String(e.message || e); }
}

async function addPreset(p) {
  error.value = '';
  try { await channelsApi.add(p.id, p); await load(); }
  catch (e) { error.value = String(e.message || e); }
}

async function addCustom() {
  const k = (newCh.value.kind || '').trim().toLowerCase().replace(/\s+/g, '_');
  if (!k) { error.value = 'Укажите идентификатор канала (латиницей)'; return; }
  error.value = '';
  try {
    await channelsApi.add(k, { label: newCh.value.label || k, icon: newCh.value.icon || '🔗', group: newCh.value.group || 'Прочее' });
    newCh.value = { kind: '', label: '', icon: '🔗', group: 'Прочее' };
    showAdd.value = false;
    await load();
  } catch (e) { error.value = String(e.message || e); }
}

function webhookUrl(kind) {
  return `${origin}/webhooks/channel/${kind}`;
}
async function copyHook(kind) {
  try { await navigator.clipboard.writeText(webhookUrl(kind)); okMsg.value = 'URL скопирован'; }
  catch { /* буфер обмена недоступен — URL и так виден */ }
}

const groups = computed(() => {
  const g = {};
  for (const ch of items.value) (g[ch.group] = g[ch.group] || []).push(ch);
  return Object.entries(g);
});
</script>

<template>
  <div class="channels-page">
    <div class="row" style="justify-content:space-between;align-items:center">
      <div>
        <h2 style="margin:0">Каналы CRM</h2>
        <div class="mini muted">Мессенджеры, соцсети и площадки — подключаются здесь, без редактирования конфигов.</div>
      </div>
      <button class="btn" @click="showAdd = !showAdd">＋ Свой канал</button>
    </div>

    <div v-if="!apiState.online" class="mini warn-box">
      Бэкенд недоступен — управление каналами работает только с подключённым сервером.
    </div>
    <div v-if="error" class="mini err-box">{{ error }}</div>
    <div v-if="okMsg" class="mini ok-box">{{ okMsg }}</div>

    <div v-if="showAdd" class="card add-card">
      <div class="grid2">
        <label class="field"><span>Идентификатор (a-z)</span><input v-model="newCh.kind" class="input" placeholder="youtube" /></label>
        <label class="field"><span>Название</span><input v-model="newCh.label" class="input" placeholder="YouTube" /></label>
        <label class="field"><span>Иконка (эмодзи)</span><input v-model="newCh.icon" class="input" placeholder="▶️" /></label>
        <label class="field"><span>Группа</span><input v-model="newCh.group" class="input" placeholder="Соцсети" /></label>
      </div>
      <button class="btn btn-primary" @click="addCustom">Добавить канал</button>
    </div>

    <div v-if="loading" class="mini muted">Загрузка каналов…</div>

    <section v-for="[grp, list] in groups" :key="grp" class="grp">
      <h3 class="grp-title">{{ grp }}</h3>
      <div class="ch-grid">
        <div v-for="ch in list" :key="ch.id" class="card ch-card" :class="{ off: !ch.enabled }">
          <div class="row" style="align-items:center;gap:8px">
            <span class="ch-icon" :style="{ background: ch.color + '22', color: ch.color }">{{ ch.icon }}</span>
            <div style="flex:1">
              <div class="ch-name">{{ ch.label }}</div>
              <div class="mini muted">
                <span v-if="ch.connected" class="ok-dot">●</span>
                {{ ch.accounts.length ? `${ch.accounts.length} аккаунт(ов)` : 'не подключён' }}
              </div>
            </div>
            <label class="switch mini" :title="ch.enabled ? 'Канал включён' : 'Канал отключён'">
              <input type="checkbox" :checked="ch.enabled" @change="toggleChannel(ch)" />
            </label>
          </div>

          <ul v-if="ch.accounts.length" class="acc-list">
            <li v-for="acc in ch.accounts" :key="acc.id" class="acc">
              <span>{{ acc.displayName || acc.login || ch.label }}</span>
              <span v-if="acc.tokenMask" class="mini mono muted">{{ acc.tokenMask }}</span>
              <button class="link-btn" @click="removeAccount(ch, acc)">отключить</button>
            </li>
          </ul>

          <div class="row" style="gap:8px;margin-top:8px">
            <button class="btn btn-sm" @click="openConnect(ch)">🔌 Подключить аккаунт</button>
            <button class="btn btn-sm ghost" @click="hookOpen = hookOpen === ch.id ? null : ch.id">📥 Как приводить сообщения</button>
          </div>

          <div v-if="hookOpen === ch.id" class="hook-box">
            <div class="mini">Отправляйте входящие сообщения на этот URL (n8n/Zapier/скрипт-парсер площадки):</div>
            <div class="row" style="gap:6px;align-items:center">
              <code class="mono hook-url">POST {{ webhookUrl(ch.id) }}</code>
              <button class="link-btn" @click="copyHook(ch.id)">копировать</button>
            </div>
            <pre class="mono hook-body">{ "text": "Здравствуйте! Сколько стоит торф?",
  "contact": "Иван", "handle": "@ivan", "phone": "+996…" }</pre>
            <div class="mini muted">Если у аккаунта задан секрет — отправляйте его в заголовке X-Webhook-Secret. Сообщения автоматически привяжутся к клиенту по телефону/нику.</div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="availablePresets.length" class="grp">
      <h3 class="grp-title">Доступные для подключения</h3>
      <div class="preset-row">
        <button v-for="p in availablePresets" :key="p.id" class="chip" @click="addPreset(p)">
          {{ p.icon }} {{ p.label }} ＋
        </button>
      </div>
      <div class="mini muted">Один клик — канал появится выше, останется подключить аккаунт.</div>
    </section>

    <!-- модалка подключения -->
    <div v-if="connectFor" class="overlay" @click.self="closeConnect">
      <div class="modal">
        <h3 style="margin-top:0">{{ connectFor.icon }} Подключение · {{ connectFor.label }}</h3>
        <label class="field"><span>Логин / номер / название аккаунта</span>
          <input v-model="form.login" class="input" placeholder="@biotorf_bot / 770123456 / аккаунт Авито" /></label>
        <label class="field"><span>Отображаемое имя (в ленте)</span>
          <input v-model="form.displayName" class="input" :placeholder="connectFor.label" /></label>
        <label class="field"><span>Токен доступа</span>
          <input v-model="form.token" class="input" type="password" autocomplete="off"
                 :placeholder="TOKEN_HINTS[connectFor.id] || TOKEN_HINTS.default" /></label>
        <label class="field"><span>{{ SECRET_LABELS[connectFor.id] || SECRET_LABELS.default }}</span>
          <input v-model="form.secret" class="input" type="password" autocomplete="off" placeholder="придумайте длинный случайный секрет" /></label>
        <div class="mini muted">Секреты хранятся на сервере и никогда не возвращаются в браузер (маска вида 123…h1).</div>
        <div class="row" style="gap:8px;margin-top:10px;justify-content:flex-end">
          <button class="btn" @click="closeConnect">Отмена</button>
          <button class="btn btn-primary" :disabled="busy || !form.login" @click="doConnect">
            {{ busy ? 'Подключение…' : 'Подключить' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.channels-page { padding: 4px; }
.grp { margin-top: 18px; }
.grp-title { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted, #888); margin: 0 0 8px; }
.ch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.ch-card { padding: 12px; }
.ch-card.off { opacity: .55; }
.ch-icon { width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px; }
.ch-name { font-weight: 600; }
.ok-dot { color: #2ecc71; }
.acc-list { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.acc { display: flex; gap: 8px; align-items: center; justify-content: space-between; font-size: 13px; background: rgba(127,127,127,.08); border-radius: 8px; padding: 4px 8px; }
.link-btn { background: none; border: none; color: #e5484d; cursor: pointer; font-size: 12px; padding: 0; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.ghost { background: transparent; border: 1px solid rgba(127,127,127,.35); }
.hook-box { margin-top: 10px; padding: 10px; border-radius: 10px; background: rgba(127,127,127,.08); display: flex; flex-direction: column; gap: 6px; }
.hook-url { font-size: 11px; word-break: break-all; background: rgba(0,0,0,.06); padding: 3px 6px; border-radius: 6px; }
.hook-body { font-size: 11px; margin: 0; white-space: pre-wrap; background: rgba(0,0,0,.06); padding: 8px; border-radius: 8px; }
.preset-row { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { border: 1px dashed rgba(127,127,127,.45); background: transparent; border-radius: 999px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
.chip:hover { border-color: var(--accent, #2aabee); }
.overlay { position: fixed; inset: 0; background: rgba(10, 14, 18, .72); backdrop-filter: none; display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { width: min(460px, 92vw); padding: 16px; background: #ffffff; color: #1c2430; border: 1px solid rgba(127,127,127,.35); box-shadow: 0 18px 48px rgba(0,0,0,.35); opacity: 1; }
.modal .input { background: #f4f6f8; color: #1c2430; }
.modal .btn { background: #eef1f4; color: #1c2430; }
.modal .btn-primary { background: var(--accent, #2aabee); color: #fff; border-color: transparent; }
.modal .mini.muted { opacity: 1; color: #5b6675; }
.field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; font-size: 12px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.add-card { margin-top: 12px; padding: 12px; }
.err-box { color: #e5484d; } .ok-box { color: #2ecc71; } .warn-box { color: #f5a623; }
.mono { font-family: ui-monospace, monospace; }
.input { padding: 7px 10px; border-radius: 8px; border: 1px solid rgba(127,127,127,.35); background: transparent; color: inherit; }
.btn { padding: 7px 14px; border-radius: 8px; border: 1px solid rgba(127,127,127,.35); background: transparent; cursor: pointer; color: inherit; }
.btn-primary { background: var(--accent, #2aabee); color: #fff; border-color: transparent; }
.btn:disabled { opacity: .5; cursor: default; }
.mini { font-size: 12px; } .muted { opacity: .7; }
.card { border-radius: 12px; border: 1px solid rgba(127,127,127,.2); background: rgba(127,127,127,.04); }
.row { display: flex; }
.switch input { transform: scale(1.2); cursor: pointer; }
</style>
