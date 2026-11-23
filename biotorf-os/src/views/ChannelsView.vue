<script setup>
import { ref, computed, nextTick, onMounted } from 'vue';
import { channelsApi } from '../api/channelsClient';
import { COMMS_API_URL, commsApi } from '../api/commsClient';
import ChannelIcon from '@/components/ChannelIcon.vue';
import { useUiStore } from '@/stores/ui';

const ui = useUiStore();
const canConnect = computed(() => ui.role === 'director');
const canManage = computed(() => canConnect.value || ui.role === 'operations');

const items = ref([]);
const presets = ref([]);
const loading = ref(false);
const error = ref('');
const okMsg = ref('');
const capabilities = ref(null);

const connectFor = ref(null);
const connectForms = ref([]);
const form = ref({ login: '', displayName: '', token: '', secret: '' });
const busy = ref(false);
const connectError = ref('');

// форма добавления своего канала
const showAdd = ref(false);
const newCh = ref({ kind: '', label: '', icon: '🔗', group: 'Прочее' });

// раскрывающийся список вебхука
const hookOpen = ref(null);
const native = {
  telegram: {
    url: '/webhooks/telegram',
    login: 'Имя бота', loginHint: '@biotorf_bot',
    tokenHint: 'Токен бота из @BotFather',
    secret: 'Секрет вебхука Telegram',
    help: 'Укажите этот адрес при настройке вебхука Telegram. В secret_token передайте секрет, заданный на сервере или для аккаунта. Чтобы бот мог ответить, клиент должен сначала написать ему.',
  },
  whatsapp: {
    url: '/webhooks/whatsapp',
    login: 'Phone Number ID в Meta', loginHint: 'ID бизнес-номера из Meta Developers',
    tokenHint: 'Постоянный токен WhatsApp Cloud API',
    help: 'Укажите этот Callback URL в Meta Developers и подпишитесь на событие messages. Для входящих сообщений на сервере должны быть настроены App Secret и Verify Token. Для первого сообщения используйте одобренный шаблон WhatsApp.',
  },
};
const channelConfig = (kind) => Object.hasOwn(native, kind) ? native[kind] : null;

function connectionState(channel) {
  if (!channel.enabled) return 'Канал выключен';
  const status = capabilities.value?.channelStatuses?.[channel.id];
  if (status?.mode === 'direct') return 'Отправка настроена';
  if (status?.mode === 'queue') return 'Отправка через очередь';
  if (channelConfig(channel.id)) {
    if (!capabilities.value) return 'Отправка не проверена';
    if (capabilities.value[`${channel.id}Send`]) return 'Отправка настроена';
    return status?.inbound ? 'Только входящие' : 'Отправка не готова';
  }
  if (channel.id === 'call') return 'Журнал звонков';
  return status?.inbound ? 'Входящие через вебхук' : 'Нужна настройка вебхука';
}

async function load() {
  if (loading.value) return;
  loading.value = true; error.value = '';
  try {
    const [res, info] = await Promise.all([channelsApi.list(), commsApi.capabilities().catch(() => null)]);
    items.value = res.items || [];
    presets.value = res.presets || [];
    capabilities.value = info;
  } catch (e) {
    error.value = String(e.message || e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const availablePresets = computed(() =>
  presets.value.filter((p) => !items.value.some((c) => c.id === p.id)));

async function openConnect(ch) {
  if (connectFor.value?.id === ch.id) return;
  connectFor.value = ch;
  form.value = { login: '', displayName: '', token: '', secret: '' };
  connectError.value = '';
  okMsg.value = '';
  await nextTick();
  connectForms.value[0]?.elements.login.focus();
}
function closeConnect() {
  connectFor.value = null;
  form.value = { login: '', displayName: '', token: '', secret: '' };
}

async function doConnect() {
  const ch = connectFor.value;
  if (!ch || busy.value || !form.value.login.trim()) return;
  busy.value = true; connectError.value = '';
  try {
    await channelsApi.connect(ch.id, { ...form.value });
    okMsg.value = `Настройки ${ch.label} сохранены.`;
    closeConnect();
    await load();
  } catch (e) {
    connectError.value = e.message || 'Не удалось сохранить настройки канала.';
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
  return COMMS_API_URL.replace(/\/+$/, '') + (channelConfig(kind)?.url || `/webhooks/channel/${encodeURIComponent(kind)}`);
}
async function copyHook(kind) {
  try { await navigator.clipboard.writeText(webhookUrl(kind)); okMsg.value = 'Адрес вебхука скопирован.'; }
  catch { /* буфер обмена недоступен — URL и так виден */ }
}

const groups = computed(() => {
  const rows = new Map();
  for (const channel of items.value) {
    if (!rows.has(channel.group)) rows.set(channel.group, []);
    rows.get(channel.group).push(channel);
  }
  return [...rows];
});
</script>

<template>
  <div class="channels-page">
    <div class="row" style="justify-content:space-between;align-items:center">
      <div>
        <h2 style="margin:0">Каналы CRM</h2>
        <div class="mini muted">Подключения мессенджеров и источники входящих сообщений.</div>
      </div>
      <div class="actionbar">
        <a class="btn slim ghost" href="#/comms">К переписке</a>
        <button class="btn slim" type="button" :disabled="loading" @click="load">Обновить статусы</button>
        <button v-if="canManage" class="btn slim" type="button" :aria-expanded="showAdd" @click="showAdd = !showAdd">＋ Свой канал</button>
      </div>
    </div>

    <div v-if="error" class="mini err-box" role="alert">{{ error }}</div>
    <div v-if="okMsg" class="mini ok-box" role="status">{{ okMsg }}</div>

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
            <span class="ch-icon"><ChannelIcon :kind="ch.id" :size="23" :fallback="ch.icon" /></span>
            <div style="flex:1">
              <div class="ch-name">{{ ch.label }}</div>
              <div class="mini muted">
                {{ connectionState(ch) }}
              </div>
            </div>
            <label v-if="canManage" class="switch mini" :title="ch.enabled ? 'Канал включён' : 'Канал отключён'">
              <input type="checkbox" role="switch" :aria-label="`${ch.label} включён`" :checked="ch.enabled" @change="toggleChannel(ch)" />
            </label>
          </div>

          <ul v-if="ch.accounts.length" class="acc-list">
            <li v-for="acc in ch.accounts" :key="acc.id" class="acc">
              <span>{{ acc.displayName || acc.login || ch.label }}</span>
              <span v-if="acc.tokenMask" class="mini mono muted">{{ acc.tokenMask }}</span>
              <button v-if="canManage" class="link-btn" @click="removeAccount(ch, acc)">Отключить</button>
            </li>
          </ul>

          <div class="row" style="gap:8px;margin-top:8px">
            <button v-if="canConnect" class="btn btn-sm" :disabled="busy" :aria-expanded="connectFor?.id === ch.id" @click="openConnect(ch)">Подключить аккаунт</button>
            <button class="btn btn-sm ghost" :aria-expanded="hookOpen === ch.id" @click="hookOpen = hookOpen === ch.id ? null : ch.id">Настройка входящих</button>
          </div>

          <form v-if="connectFor?.id === ch.id" ref="connectForms" class="account-form" aria-label="Подключение аккаунта" @submit.prevent="doConnect">
            <h4>Подключение · {{ ch.label }}</h4>
            <label class="field"><span>{{ channelConfig(ch.id)?.login || 'Название источника' }}</span>
              <input v-model.trim="form.login" name="login" class="input" required :inputmode="ch.id === 'whatsapp' ? 'numeric' : undefined"
                :pattern="ch.id === 'whatsapp' ? '[0-9]+' : undefined" :placeholder="channelConfig(ch.id)?.loginHint || ch.label" /></label>
            <label class="field"><span>Отображаемое имя (в ленте)</span>
              <input v-model="form.displayName" class="input" :placeholder="ch.label" /></label>
            <label v-if="channelConfig(ch.id)" class="field"><span>Токен доступа</span>
              <input v-model.trim="form.token" class="input" type="password" autocomplete="off" required
                     :placeholder="channelConfig(ch.id).tokenHint" /></label>
            <label v-if="ch.id !== 'whatsapp'" class="field"><span>{{ channelConfig(ch.id)?.secret || 'Секрет вебхука' }}</span>
              <input v-model.trim="form.secret" class="input" type="password" autocomplete="off" required
                :pattern="ch.id === 'telegram' ? '[A-Za-z0-9_\\-]{1,256}' : undefined" /></label>
            <div v-if="ch.id === 'whatsapp'" class="mini muted">App Secret и Verify Token для входящих сообщений задаются на сервере.</div>
            <div v-else class="mini muted">Секрет хранится на сервере.</div>
            <div v-if="connectError" class="mini err-box" role="alert">{{ connectError }}</div>
            <div class="row account-actions">
              <button class="btn" type="button" :disabled="busy" @click="closeConnect">Отмена</button>
              <button class="btn btn-primary" type="submit" :disabled="busy || !form.login.trim()">
                {{ busy ? 'Подключение…' : 'Подключить' }}
              </button>
            </div>
          </form>

          <div v-if="hookOpen === ch.id" class="hook-box">
            <div class="mini">{{ channelConfig(ch.id)?.help || 'Укажите этот адрес в коннекторе, который будет передавать входящие сообщения из сервиса.' }}</div>
            <div class="row" style="gap:6px;align-items:center">
              <code class="mono hook-url">POST {{ webhookUrl(ch.id) }}</code>
              <button class="btn btn-sm" @click="copyHook(ch.id)">Копировать адрес</button>
            </div>
            <template v-if="!channelConfig(ch.id)">
              <pre class="mono hook-body">{ "text": "Здравствуйте! Сколько стоит BioTorf Agro?",
  "contact": "Иван", "handle": "@ivan", "phone": "+996…" }</pre>
              <div class="mini muted">Передайте секрет источника в заголовке X-Webhook-Secret. CRM попробует найти клиента по телефону или имени пользователя.</div>
            </template>
          </div>
        </div>
      </div>
    </section>

    <section v-if="canManage && availablePresets.length" class="grp">
      <h3 class="grp-title">Доступные для подключения</h3>
      <div class="preset-row">
        <button v-for="p in availablePresets" :key="p.id" class="chip" @click="addPreset(p)">
          <ChannelIcon :kind="p.id" :size="16" :fallback="p.icon" /> {{ p.label }} ＋
        </button>
      </div>
      <div class="mini muted">Один клик — канал появится выше, останется подключить аккаунт.</div>
    </section>
  </div>
</template>

<style scoped>
.channels-page { padding: 4px; }
.grp { margin-top: 18px; }
.grp-title { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted, #888); margin: 0 0 8px; }
.ch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 12px; }
.ch-card { padding: 12px; }
.ch-card.off { background: var(--surface-soft); }
.ch-icon { width: 36px; height: 36px; flex: 0 0 auto; border-radius: 10px; display: grid; place-items: center; background: var(--surface-soft); border: 1px solid var(--border); }
.ch-name { font-weight: 600; }
.acc-list { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.acc { display: flex; gap: 8px; align-items: center; justify-content: space-between; font-size: 13px; background: rgba(127,127,127,.08); border-radius: 8px; padding: 4px 8px; }
.link-btn { background: none; border: none; color: #e5484d; cursor: pointer; font-size: 12px; padding: 0; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.ghost { background: transparent; border: 1px solid rgba(127,127,127,.35); }
.hook-box { margin-top: 10px; padding: 10px; border-radius: 10px; background: rgba(127,127,127,.08); display: flex; flex-direction: column; gap: 6px; }
.hook-url { font-size: 11px; word-break: break-all; background: rgba(0,0,0,.06); padding: 3px 6px; border-radius: 6px; }
.hook-body { font-size: 11px; margin: 0; white-space: pre-wrap; background: rgba(0,0,0,.06); padding: 8px; border-radius: 8px; }
.preset-row { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: inline-flex; align-items: center; gap: 6px; border: 1px dashed var(--control-border); background: transparent; color: var(--ink); border-radius: 999px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
.chip:hover { border-color: var(--accent, #2aabee); }
.account-form { margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(127,127,127,.2); }
.account-form h4 { margin: 0 0 12px; }
.account-actions { flex-wrap: wrap; gap: 8px; margin-top: 10px; justify-content: flex-end; }
.field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; font-size: 12px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.add-card { margin-top: 12px; padding: 12px; }
.err-box { color: var(--danger-ink); } .ok-box { color: var(--accent-ink); }
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
