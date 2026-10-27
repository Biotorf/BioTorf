<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { apiState, COMMS_API_URL, caps, commsApi } from '@/api/commsClient';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const ui = useUiStore();

// ── режим страницы: мессенджер (чаты) / лента ─────────────────────
const MODE_KEY = 'biotorf_comms_mode';
const mode = ref(localStorage.getItem(MODE_KEY) || 'chats');   // 'chats' | 'feed'
function setMode(m) { mode.value = m; localStorage.setItem(MODE_KEY, m); }

// ── состояние чатов (как в Telegram) ─────────────────────────────
const chatList = ref([]);          // [{key,kind,farmId,contact,phone,handle,unread,lastMessage,draft,messages}]
const activeKey = ref(null);       // открытый диалог
const chatInput = ref('');
const chatSending = ref(false);
const chatError = ref('');
const chatNotice = ref('');
const newChatOpen = ref(false);
const newChat = ref({ kind: 'telegram', handle: '', phone: '', contact: '' });

// ── динамические каналы (реестр бэкенда: Instagram, VK, Авито и т.д.) ──
import { channelsApi } from '../api/channelsClient';
const dynChannels = ref([]);            // [{id,label,icon,color,connected}]
async function loadChannels() {
  if (!apiState.online) return;
  try {
    const res = await channelsApi.list();
    dynChannels.value = (res.items || []).filter((c) => c.enabled && !['call', 'telegram', 'whatsapp'].includes(c.id));
  } catch { /* оффлайн — остаёмся на статичных каналах */ }
}
const channelMeta = computed(() => {
  const m = { ...KIND_META };
  for (const ch of dynChannels.value) m[ch.id] = { label: ch.label, icon: ch.icon };
  return m;
});
const connectedIds = computed(() => new Set(dynChannels.value.filter((c) => c.connected).map((c) => c.id)));
let draftTimer = null;
let firstLoad = true;

function peerTitle(c) {
  if (c.farmId) return db.farmById(c.farmId)?.name || c.farmId;
  return c.contact || c.handle || c.phone || 'Неизвестный контакт';
}
function peerSub(c) {
  const parts = [c.contact, c.handle, c.phone].filter(Boolean);
  return parts.join(' · ');
}
function fmtDay(iso) {
  const d = new Date(iso), today = new Date();
  if (d.toDateString() === today.toDateString()) return 'Сегодня';
  const yst = new Date(today.getTime() - 864e5);
  if (d.toDateString() === yst.toDateString()) return 'Вчера';
  return d.toLocaleDateString('ru-RU');
}
function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}
function dayGap(list, i) {
  if (!i) return true;
  return new Date(list[i].ts).toDateString() !== new Date(list[i - 1].ts).toDateString();
}

const activeChat = computed(() => chatList.value.find((c) => c.key === activeKey.value) || null);
const sortedChats = computed(() =>
  [...chatList.value].sort((a, b) => (a.lastTs < b.lastTs ? 1 : -1))
    .filter((c) => {
      const q = ui.search.toLowerCase();
      if (!q) return true;
      return [peerTitle(c), c.contact, c.handle, c.phone, c.lastMessage?.text]
        .filter(Boolean).join(' ').toLowerCase().includes(q);
    })
);
const totalUnread = computed(() => chatList.value.reduce((s, c) => s + (c.unread || 0), 0));
const chatMessages = computed(() => (activeChat.value?.messages || []).slice(-300));

async function loadChats(quiet = false) {
  if (!apiState.online) return;
  try {
    const res = await commsApi.chats();
    chatList.value = res.items || [];
    if (firstLoad && !activeKey.value && chatList.value.length) {
      const withUnread = chatList.value.find((c) => c.unread > 0);
      openChat(withUnread || chatList.value[0], false);
    }
    firstLoad = false;
  } catch (e) {
    if (!quiet) chatError.value = e.message || 'Не удалось загрузить чаты';
  }
}

function openChat(c, doRead = true) {
  activeKey.value = c.key;
  chatInput.value = c.draft || '';
  chatError.value = '';
  chatNotice.value = '';
  if (doRead && c.unread) {
    c.unread = 0;
    commsApi.markChatRead(c.key).catch(() => {});
  }
  scrollBottom();
}

const msgBox = ref(null);
function scrollBottom() {
  requestAnimationFrame(() => {
    if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight;
  });
}

async function sendChat() {
  const c = activeChat.value;
  const text = chatInput.value.trim();
  if (!c || !text || chatSending.value) return;
  chatSending.value = true;
  chatError.value = '';
  try {
    const res = await commsApi.sendToChat(c.key, text);
    chatNotice.value = res.sent
      ? '✅ Доставлено'
      : '⏳ Отправлено — уйдёт клиенту, как только канал будет готов';
    chatInput.value = '';
    commsApi.saveDraft(c.key, '').catch(() => {});
    await loadChats(true);
    const fresh = activeChat.value;
    if (fresh) fresh.draft = '';
    scrollBottom();
    setTimeout(() => { chatNotice.value = ''; }, 2500);
  } catch (e) {
    chatError.value = e.message || 'Сервер отклонил отправку';
  } finally {
    chatSending.value = false;
  }
}

function onInput() {
  const c = activeChat.value;
  if (!c) return;
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => {
    commsApi.saveDraft(c.key, chatInput.value).catch(() => {});
  }, 700);
}

const HANDLE_KINDS = ['telegram', 'instagram', 'facebook', 'vk', 'ok'];   // каналы с ником/URL вместо номера

async function startNewChat() {
  const f = newChat.value;
  const byPhone = !HANDLE_KINDS.includes(f.kind);
  const target = (byPhone ? f.phone : f.handle).trim();
  if (!target) { chatError.value = byPhone ? 'Укажите номер телефона' : 'Укажите ник / ссылку на профиль'; return; }
  const entry = {
    kind: f.kind, dir: 'out',
    contact: f.contact.trim() || null,
    phone: byPhone ? target : null,
    handle: !byPhone ? target.replace(/^@/, '') : null,
    text: chatInput.value.trim() || 'Новый диалог',
    read: true,
  };
  try {
    await db.addComm(entry);           // создаёт сообщение и peer_key на сервере
    newChatOpen.value = false;
    chatInput.value = '';
    await loadChats(true);
    const created = chatList.value.find((c) =>
      (entry.handle && c.handle === entry.handle) || (entry.phone && c.phone === entry.phone));
    if (created) openChat(created, false);
  } catch (e) {
    chatError.value = e.message || 'Не удалось начать диалог';
  }
}

function chatGoClient(c) {
  if (c.farmId) ui.openClient(c.farmId);
}

const KIND_META = {
  call:     { label: 'Звонок',   icon: '☎' },
  telegram: { label: 'Telegram', icon: '✈' },
  whatsapp: { label: 'WhatsApp', icon: '◔' },
};

const BASE_FILTERS = [
  ['all', 'Все'],
  ['call', 'Звонки'],
  ['telegram', 'Telegram'],
  ['whatsapp', 'WhatsApp'],
];
const FILTERS = computed(() => [
  ...BASE_FILTERS,
  ...dynChannels.value.map((c) => [c.id, `${c.icon} ${c.label}`]),
  ['unread', 'Непрочитанные'],
]);

// ── форма «зафиксировать коммуникацию» ────────────────────────────
const showForm = ref(false);
const form = ref({
  kind: 'call',
  dir: 'in',
  farmId: '',
  contact: '',
  phone: '',
  handle: '',
  text: '',
  note: '',
  status: 'Разговор',
  durationMin: 3,
});

function saveComm() {
  const f = form.value;
  if (f.kind === 'call') {
    db.addComm({
      kind: 'call',
      dir: f.dir,
      farmId: f.farmId || null,
      contact: f.contact || null,
      phone: f.phone || null,
      status: f.status,
      duration: Math.max(0, Number(f.durationMin) || 0) * 60,
      note: f.note || '',
      read: true,
    });
  } else {
    db.addComm({
      kind: f.kind,
      dir: f.dir,
      farmId: f.farmId || null,
      contact: f.contact || null,
      phone: HANDLE_KINDS.includes(f.kind) ? null : (f.phone || null),
      handle: HANDLE_KINDS.includes(f.kind) ? (f.handle || null) : null,
      text: f.text || '',
      read: true,
    });
  }
  showForm.value = false;
  form.value.text = '';
  form.value.note = '';
}

// ── быстрая запись ответа в ленте ────────────────────────────────
const replyTarget = ref(null);   // объект comms, которому отвечаем
const replyText = ref('');
const sendingReply = ref(false);
const replyError = ref('');
const replyNotice = ref('');     // «ушёл в очередь» и т.п.

function startReply(c) {
  replyTarget.value = c;
  replyText.value = '';
  replyError.value = '';
}

async function sendReply() {
  const c = replyTarget.value;
  if (!c || !replyText.value.trim()) return;
  const text = replyText.value.trim();
  // С сервером — реальный ответ клиенту в Telegram (sendMessage через бэкенд/воркер).
  // Без сервера или для WhatsApp — ответ фиксируется в ленте как исходящая запись.
  if (apiState.online && c.kind === 'telegram') {
    sendingReply.value = true;
    replyError.value = '';
    try {
      const res = await db.sendCommReply(c.id, text);
      replyNotice.value = res.sent
        ? '✅ Ответ доставлен клиенту в Telegram'
        : '⏳ Ответ принят и уйдёт клиенту, как только бот получит соединение';
      // если ушёл в очередь — сразу подтянем ленту: воркер забирает ответы
      // пачками раз в несколько секунд, статус «Доставлено» появится сам
      if (!res.sent) setTimeout(() => db.syncComms(true), 1500);
      setTimeout(() => { replyTarget.value = null; replyText.value = ''; replyNotice.value = ''; }, 1200);
      return;
    } catch (e) {
      replyError.value = e.message || 'Сервер отклонил отправку';
      return;
    } finally {
      sendingReply.value = false;
    }
  }
  db.addComm({
    kind: c.kind,
    dir: 'out',
    farmId: c.farmId,
    contact: c.contact,
    phone: c.phone,
    handle: c.handle,
    text,
    read: true,
  });
  replyTarget.value = null;
  replyText.value = '';
}

// ── привязка неизвестного контакта к клиенту ─────────────────────
const linkingId = ref(null);
function linkFarm(c, farmId) {
  db.linkCommToFarm(c.id, farmId);
  linkingId.value = null;
}

// ── фильтры и поиск ──────────────────────────────────────────────
const unreadCount = computed(() => db.comms.filter((c) => !c.read).length);

const items = computed(() =>
  [...db.comms]
    .sort((a, b) => (a.ts < b.ts ? 1 : -1))
    .filter((c) => {
      const f = ui.commsFilter;
      if (f === 'unread' && c.read) return false;
      if (f !== 'all' && f !== 'unread' && c.kind !== f) return false;
      const q = ui.search.toLowerCase();
      if (!q) return true;
      const farm = c.farmId ? db.farmById(c.farmId)?.name : '';
      return [farm, c.contact, c.phone, c.handle, c.text, c.note]
        .filter(Boolean).join(' ').toLowerCase().includes(q);
    })
);

function fmtTs(iso) {
  const d = new Date(iso);
  const today = new Date().toISOString().slice(0, 10);
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  return d.toISOString().slice(0, 10) === today ? `Сегодня ${time}` : `${d.toLocaleDateString('ru-RU')} ${time}`;
}

function fmtDur(sec) {
  if (!sec) return '—';
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')} мин`;
}

function open(c) {
  if (!c.read) db.markCommRead(c.id);
  if (c.farmId) ui.openClient(c.farmId);
}

// ── автообновление ленты: входящие сообщения и статусы доставки ответов
// подтягиваются с сервера сами, без ручного F5 ──────────────────────
const autoRefresh = ref(true);
let pollTimer = null;

async function tick() {
  if (!autoRefresh.value || document.hidden) return;
  await db.syncComms(true);   // quiet — не шумим ошибкой при временном недоступе API
  if (mode.value === 'chats') await loadChats(true);
}

onMounted(async () => {
  // если поднят бэкенд коммуникаций (backend/, порт 8787) — лента общая, из SQLite
  await db.syncComms();
  await loadChannels();
  await loadChats(true);
  pollTimer = setInterval(tick, 4000);
  window.addEventListener('focus', tick);   // сразу обновляемся при возврате во вкладку
  if (ui.commsFocusFarm) {
    ui.search = db.farmById(ui.commsFocusFarm)?.name || '';
    ui.commsFocusFarm = null;
  }
});

onBeforeUnmount(() => {
  clearInterval(pollTimer);
  window.removeEventListener('focus', tick);
});
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Коммуникации</h1>
        <div class="subtitle">Единая лента: звонки с телефона, Telegram и WhatsApp. Всё общение с клиентом — внутри сервиса.</div>
      <BackendBadge collection="comms" />
      </div>
      <div class="actionbar">
        <label class="mini" style="display:flex;align-items:center;gap:6px;cursor:pointer" title="Лента и статусы доставки подтягиваются с сервера каждые 4 секунды">
          <input type="checkbox" v-model="autoRefresh" /> автообновление
        </label>
        <button class="btn slim ghost" @click="db.markAllCommsRead()" :disabled="!unreadCount">
          Прочитано всё ({{ unreadCount }})
        </button>
        <button class="btn primary" @click="showForm = !showForm">＋ Зафиксировать</button>
      </div>
    </div>

    <div class="note">
      <template v-if="apiState.online">
        ✅ Лента синхронизируется с сервером ({{ COMMS_API_URL }}): общая база звонков и сообщений
        для всех сотрудников. Входящие из Telegram/WhatsApp/телефонии поступают автоматически
        через вебхуки бэкенда (<code>/webhooks/*</code>).
      </template>
      <template v-else>
        Лента работает локально (без бэкенда): сообщения фиксируются вручную и видны только в
        этом браузере. Запустите стек — <code>docker compose up -d --build</code> (или локально
        <code>cd backend && uvicorn main:app --port 8787</code>) — и лента станет общей, с
        автоприёмом из IP-телефонии, Telegram Bot API и WhatsApp Business API.
      </template>
      <div v-if="db.commsSyncError" style="color:#b42318;margin-top:6px">
        Ошибка синхронизации: {{ db.commsSyncError }}
      </div>
    </div>

    <div v-if="showForm" class="panel" style="margin-bottom:18px">
      <div class="panel-head"><span class="panel-title">Новая коммуникация</span></div>
      <div class="formgrid">
        <div class="field">
          <label>Канал</label>
          <select v-model="form.kind" class="select">
            <option value="call">Звонок (телефония)</option>
            <option value="telegram">Telegram</option>
            <option value="whatsapp">WhatsApp</option>
            <option v-for="ch in dynChannels" :key="ch.id" :value="ch.id">{{ ch.icon }} {{ ch.label }}</option>
          </select>
        </div>
        <div class="field">
          <label>Направление</label>
          <select v-model="form.dir" class="select">
            <option value="in">Входящее</option>
            <option value="out">Исходящее</option>
          </select>
        </div>
        <div class="field">
          <label>Клиент / хозяйство</label>
          <select v-model="form.farmId" class="select">
            <option value="">— не определён —</option>
            <option v-for="f in db.farms" :key="f.id" :value="f.id">{{ f.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>Контактное лицо</label>
          <input v-model="form.contact" class="input" placeholder="Имя / должность" />
        </div>
        <div v-if="!HANDLE_KINDS.includes(form.kind)" class="field">
          <label>Номер телефона</label>
          <input v-model="form.phone" class="input" placeholder="+996 …" />
        </div>
        <div v-else class="field">
          <label>{{ form.kind === 'telegram' ? 'Ник в Telegram' : 'Ник / ссылка на профиль' }}</label>
          <input v-model="form.handle" class="input" :placeholder="form.kind === 'telegram' ? '@username' : 'например @client или https://…'" />
        </div>
        <template v-if="form.kind === 'call'">
          <div class="field">
            <label>Итог звонка</label>
            <select v-model="form.status" class="select">
              <option>Разговор</option>
              <option>Пропущенный</option>
              <option>Не дозвонились</option>
              <option>Перезвонить позже</option>
            </select>
          </div>
          <div class="field">
            <label>Длительность, мин</label>
            <input v-model.number="form.durationMin" type="number" min="0" class="input" />
          </div>
          <div class="field full">
            <label>Резюме разговора</label>
            <textarea v-model="form.note" class="textarea" placeholder="О чём договорились, следующие шаги…"></textarea>
          </div>
        </template>
        <div v-else class="field full">
          <label>Сообщение</label>
          <textarea v-model="form.text" class="textarea" placeholder="Текст сообщения…"></textarea>
        </div>
      </div>
      <div class="modal-foot" style="padding:14px 0 0;border-top:0">
        <button class="btn ghost" @click="showForm = false">Отмена</button>
        <button class="btn primary" @click="saveComm">Сохранить в ленту</button>
      </div>
    </div>

    <div class="chips toolbar" style="margin-bottom:14px">
      <button class="chip" :class="{ selected: mode === 'chats' }" :style="mode === 'chats' ? 'background:#27b95a;color:#fff' : ''" @click="setMode('chats')">
        💬 Чаты<template v-if="totalUnread"> · {{ totalUnread }}</template>
      </button>
      <button class="chip" :class="{ selected: mode === 'feed' }" :style="mode === 'feed' ? 'background:#27b95a;color:#fff' : ''" @click="setMode('feed')">
        📋 Лента (все коммуникации)
      </button>
    </div>

    <!-- ═══ МЕССЕНДЖЕР: ЧАТЫ ═══ -->
    <div v-if="mode === 'chats'" class="messenger">
      <div v-if="!apiState.online" class="note">
        💬 Режим чатов доступен при поднятом бэкенде. Запустите стек (<code>docker compose up -d --build</code>) —
        или переключитесь на ленту, чтобы работать локально.
      </div>
      <template v-else>
        <aside class="chat-side">
          <div class="chat-side-head">
            <span class="panel-title">Чаты</span>
            <button class="btn slim primary" @click="newChatOpen = !newChatOpen">＋ Диалог</button>
          </div>
          <div v-if="newChatOpen" class="newchat">
            <select v-model="newChat.kind" class="select">
              <option value="telegram">✈ Telegram</option>
              <option value="whatsapp">◔ WhatsApp</option>
              <option v-for="ch in dynChannels" :key="ch.id" :value="ch.id">{{ ch.icon }} {{ ch.label }}</option>
            </select>
            <div v-if="!connectedIds.has(newChat.kind) && newChat.kind !== 'telegram' && newChat.kind !== 'whatsapp'" class="mini muted">
              ⚠ Аккаунт этого канала ещё не подключён — сообщения сохранятся в ленте. Привязать аккаунт можно в «Настройки → Каналы CRM».
            </div>
            <input v-if="HANDLE_KINDS.includes(newChat.kind)" v-model="newChat.handle" class="input" placeholder="@ник клиента / ссылка на профиль" />
            <input v-else v-model="newChat.phone" class="input" placeholder="+996 … номер" />
            <input v-model="newChat.contact" class="input" placeholder="Имя (необязательно)" />
            <textarea v-model="chatInput" class="textarea" rows="2" placeholder="Первое сообщение…"></textarea>
            <button class="btn primary slim" @click="startNewChat">Начать диалог</button>
          </div>
          <div class="chat-list">
            <div
              v-for="c in sortedChats" :key="c.key"
              class="chat-item" :class="{ active: c.key === activeKey, unread: c.unread }"
              @click="openChat(c)"
            >
              <div class="avatar" :class="'av-' + c.kind">{{ channelMeta[c.kind]?.icon || '💬' }}</div>
              <div class="chat-item-main">
                <div class="chat-item-top">
                  <span class="chat-name">{{ peerTitle(c) }}</span>
                  <span class="chat-time mini">{{ fmtTime(c.lastTs) }}</span>
                </div>
                <div class="chat-item-bottom">
                  <span class="chat-preview">{{ c.lastMessage?.dir === 'out' ? '→ ' : '' }}{{ (c.lastMessage?.text || '').slice(0, 60) }}</span>
                  <span v-if="c.unread" class="badge">{{ c.unread }}</span>
                </div>
              </div>
            </div>
            <div v-if="!sortedChats.length" class="empty" style="padding:18px">Диалогов пока нет.</div>
          </div>
        </aside>

        <section class="chat-window">
          <template v-if="activeChat">
            <header class="chat-head">
              <div>
                <div class="chat-head-name" :class="{ 'txt-link': !!activeChat.farmId }" @click="chatGoClient(activeChat)">
                  {{ peerTitle(activeChat) }}
                </div>
                <div class="mini">{{ channelMeta[activeChat.kind]?.label || activeChat.kind }} · {{ peerSub(activeChat) || 'диалог' }}</div>
              </div>
              <span v-if="activeChat.lastOutStatus === 'Доставлено'" class="pill green">ответ доставлен ✓</span>
              <span v-else-if="activeChat.lastOutStatus === 'В очереди'" class="pill amber">⏳ в очереди</span>
              <span v-else-if="activeChat.lastOutStatus === 'Ошибка доставки'" class="pill red">✕ ошибка</span>
            </header>
            <div ref="msgBox" class="chat-messages">
              <template v-for="(m, i) in chatMessages" :key="m.seq ?? m.id">
                <div v-if="dayGap(chatMessages, i)" class="day-divider"><span>{{ fmtDay(m.ts) }}</span></div>
                <div class="msg-row" :class="m.dir === 'out' ? 'mine' : 'theirs'">
                  <div class="bubble" :class="['k-' + m.kind, { failed: m.status === 'Ошибка доставки' }]">
                    <div class="bubble-text">{{ m.text || (m.kind === 'call' ? `Звонок · ${m.status || ''}` : '') }}</div>
                    <div class="bubble-meta">
                      <span>{{ fmtTime(m.ts) }}</span>
                      <span v-if="m.dir === 'out'">
                        <template v-if="m.status === 'Доставлено'"> ✓✓</template>
                        <template v-else-if="m.status === 'В очереди'"> 🕓</template>
                        <template v-else-if="m.status === 'Ошибка доставки'"> ✕</template>
                        <template v-else> ✓</template>
                      </span>
                    </div>
                  </div>
                </div>
              </template>
              <div v-if="!chatMessages.length" class="empty" style="padding:24px">Сообщений нет — напишите первым.</div>
            </div>
            <footer class="chat-input">
              <div v-if="chatError" class="mini comms-error" style="padding:0 14px">{{ chatError }}</div>
              <div v-if="chatNotice" class="mini comms-ok" style="padding:0 14px">{{ chatNotice }}</div>
              <div class="chat-input-row">
                <textarea
                  v-model="chatInput" class="textarea chat-textarea" rows="1"
                  :placeholder="caps.telegramSend || caps.whatsappSend ? 'Сообщение… (Enter — отправить)' : 'Сохранится в ленте; отправка не настроена на сервере'"
                  @input="onInput"
                  @keydown.enter.exact.prevent="sendChat"
                ></textarea>
                <button class="btn primary send-btn" :disabled="!chatInput.trim() || chatSending" @click="sendChat">
                  {{ chatSending ? '…' : '➤' }}
                </button>
              </div>
            </footer>
          </template>
          <div v-else class="chat-empty">
            <div style="font-size:40px">💬</div>
            <div>Выберите чат слева или начните новый диалог</div>
            <div class="mini">Входящие из Telegram и WhatsApp автоматически группируются в чаты по собеседнику</div>
          </div>
        </section>
      </template>
    </div>

    <!-- ═══ ЛЕНТА (прежний табличный вид) ═══ -->
    <template v-if="mode === 'feed'">
    <div class="chips toolbar">
      <button
        v-for="[key, label] in FILTERS"
        :key="key"
        class="chip"
        :class="{ warn: key === 'unread' && unreadCount, selected: ui.commsFilter === key }"
        :style="ui.commsFilter === key ? 'background:#27b95a;color:#fff' : ''"
        @click="ui.commsFilter = key"
      >{{ label }}<template v-if="key === 'unread' && unreadCount"> · {{ unreadCount }}</template></button>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Канал</th>
            <th>Клиент</th>
            <th>Контакт</th>
            <th>Содержание</th>
            <th>Когда</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in items"
            :key="c.id"
            :class="{ actionable: !!c.farmId, 'comms-unread': !c.read }"
            @click="open(c)"
          >
            <td>
              <span class="comms-kind" :class="'k-' + c.kind">
                {{ channelMeta[c.kind]?.icon || '💬' }} {{ channelMeta[c.kind]?.label || c.kind }}
              </span>
              <div class="mini">{{ c.dir === 'in' ? '↓ входящее' : '↑ исходящее' }}</div>
            </td>
            <td>
              <template v-if="c.farmId">
                <span class="txt-link">{{ db.farmById(c.farmId)?.name || c.farmId }}</span>
              </template>
              <template v-else>
                <span class="pill amber">не привязано</span>
                <div class="mini">{{ c.phone || c.handle || 'неизвестный контакт' }}</div>
              </template>
            </td>
            <td>
              <div>{{ c.contact || '—' }}</div>
              <div class="mini mono">{{ c.phone || c.handle || '' }}</div>
            </td>
            <td style="white-space:normal;max-width:420px">
              <template v-if="c.kind === 'call'">
                <StatusPill :status="c.status" />
                <span class="mini"> · {{ fmtDur(c.duration) }}</span>
                <div class="mini" style="margin-top:3px">{{ c.note }}</div>
              </template>
              <template v-else>
                <div class="comms-bubble" :class="{ out: c.dir === 'out' }">{{ c.text }}</div>
                <div v-if="c.source === 'reply'" class="mini" style="margin-top:3px">
                  ↩ ответ на сообщение клиента
                  <span v-if="c.status === 'В очереди'" class="pill amber">⏳ в очереди на отправку</span>
                  <span v-else-if="c.status === 'Доставлено'" class="pill green">✓ доставлено</span>
                  <span v-else-if="c.status === 'Ошибка доставки'" class="pill red">✕ ошибка доставки</span>
                </div>
              </template>
            </td>
            <td class="mini">{{ fmtTs(c.ts) }}</td>
            <td @click.stop>
              <div class="actionbar" style="justify-content:flex-end">
                <button v-if="c.kind !== 'call' && c.dir === 'in'" class="btn slim ghost" @click="startReply(c)">Ответить</button>
                <button v-if="!c.farmId" class="btn slim" @click="linkingId = linkingId === c.id ? null : c.id">Привязать</button>
              </div>
              <div v-if="linkingId === c.id" style="margin-top:6px">
                <select class="select" @change="linkFarm(c, $event.target.value)">
                  <option value="">Выберите клиента…</option>
                  <option v-for="f in db.farms" :key="f.id" :value="f.id">{{ f.name }}</option>
                </select>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!items.length" class="empty">Записей нет — измените фильтр или зафиксируйте коммуникацию</div>
    </div>
    </template>

    <!-- панель быстрого ответа -->
    <Teleport to="body">
      <div v-if="replyTarget" class="modal-backdrop" @click.self="replyTarget = null">
        <div class="modal" role="dialog" aria-label="Ответ клиенту">
          <div class="modal-title">
            <h2>Ответ · {{ channelMeta[replyTarget.kind].label }}</h2>
            <button class="btn ghost slim" @click="replyTarget = null">✕</button>
          </div>
          <div class="modal-body">
            <div class="mini" style="margin-bottom:4px">Сообщение клиента · {{ fmtTs(replyTarget.ts) }}</div>
            <div class="comms-bubble" style="margin-bottom:12px">{{ replyTarget.text }}</div>
            <textarea v-model="replyText" class="textarea" rows="4" placeholder="Ваш ответ… (Ctrl+Enter — отправить)" autofocus
                      @keydown.ctrl.enter.prevent="sendReply"></textarea>
            <div v-if="apiState.online && replyTarget.kind === 'telegram' && caps.telegramSend" class="mini comms-ok" style="margin-top:8px">
              ✉ Сообщение будет реально отправлено клиенту в Telegram от имени бота{{ caps.telegramBot ? ' @' + caps.telegramBot : '' }}
            </div>
            <div v-else-if="apiState.online && replyTarget.kind === 'telegram'" class="mini comms-warn" style="margin-top:8px">
              ⚠ Отправка через бота не настроена на сервере (TELEGRAM_BOT_TOKEN пуст или отвергнут Telegram) —
              ответ сохранится только в ленте. Впишите токен из @BotFather в .env и выполните
              <code>docker compose --profile tg up -d --force-recreate</code>. Подробности: <code>docker logs biotorf-backend</code>.
            </div>
            <div v-else-if="apiState.online && replyTarget.kind === 'whatsapp' && caps.whatsappSend" class="mini comms-ok" style="margin-top:8px">
              ✉ Сообщение будет реально отправлено клиенту в WhatsApp с бизнес-номера{{ caps.whatsappPhone ? ' ' + caps.whatsappPhone : '' }}
            </div>
            <div v-else-if="apiState.online && replyTarget.kind === 'whatsapp'" class="mini comms-warn" style="margin-top:8px">
              ⚠ Отправка в WhatsApp не настроена на сервере{{ caps.whatsappError ? ': ' + caps.whatsappError : '' }} —
              ответ сохранится только в ленте. Заполните WHATSAPP_TOKEN и WHATSAPP_PHONE_NUMBER_ID в .env и выполните
              <code>docker compose up -d --force-recreate backend</code>. Подробности: README-WHATSAPP.md.
            </div>
            <div v-if="replyError" class="mini comms-error" style="margin-top:8px">{{ replyError }}</div>
            <div v-if="replyNotice" class="mini comms-ok" style="margin-top:8px">{{ replyNotice }}</div>
            <div v-else class="mini" style="margin-top:8px">
              Адресат: {{ replyTarget.contact || replyTarget.phone || replyTarget.handle || '—' }}
            </div>
          </div>
          <div class="modal-foot">
            <button class="btn ghost" @click="replyTarget = null">Отмена</button>
            <button class="btn primary" :disabled="!replyText.trim() || sendingReply" @click="sendReply">
              {{ sendingReply ? 'Отправка…' : 'Отправить' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.comms-kind { display:inline-flex; align-items:center; gap:5px; font-weight:700; font-size:12px; padding:3px 8px; border-radius:7px; white-space:nowrap; }
.k-call { background:#e7f0fb; color:#2b5fa8; }
.k-telegram { background:#e3f2fd; color:#1a7fc1; }
.k-whatsapp { background:#e4f8e8; color:#1f9a4b; }
.comms-bubble { background:#f1f6f3; border:1px solid #e0ebe4; border-radius:10px; padding:8px 11px; font-size:13px; max-width:420px; }
.comms-bubble.out { background:#e2f6e8; border-color:#cdecd6; }
.comms-unread td { background:#fffbef; }
.comms-unread td:first-child { box-shadow: inset 3px 0 0 #edaa55; }
.comms-ok { color:#1f9a4b; }
.comms-warn { color:#b54708; }
.comms-error { color:#b42318; }
.pill.green { background:#e4f8e8; color:#1f9a4b; }
.pill.red { background:#fde8e8; color:#b42318; }

/* ── мессенджер (чаты) ─────────────────────────────────────────── */
.messenger { display:flex; gap:0; border:1px solid #e2e8e0; border-radius:14px; overflow:hidden; height:min(640px, calc(100vh - 260px)); background:#fff; box-shadow:0 1px 3px rgba(20,40,30,.06); }
.chat-side { width:320px; min-width:260px; border-right:1px solid #e7ece8; display:flex; flex-direction:column; background:#fbfdfb; }
.chat-side-head { display:flex; align-items:center; justify-content:space-between; padding:12px 14px; border-bottom:1px solid #e7ece8; }
.newchat { display:flex; flex-direction:column; gap:8px; padding:12px 14px; border-bottom:1px solid #e7ece8; background:#f4faf5; }
.chat-list { flex:1; overflow-y:auto; }
.chat-item { display:flex; gap:10px; padding:11px 12px; cursor:pointer; border-bottom:1px solid #eef2ee; align-items:center; }
.chat-item:hover { background:#f1f7f2; }
.chat-item.active { background:#e2f6e8; }
.chat-item.unread .chat-name { font-weight:800; }
.avatar { width:42px; height:42px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:18px; flex-shrink:0; }
.av-telegram { background:#e3f2fd; } .av-whatsapp { background:#e4f8e8; } .av-call { background:#e7f0fb; }
.chat-item-main { flex:1; min-width:0; }
.chat-item-top { display:flex; justify-content:space-between; gap:8px; }
.chat-name { font-weight:700; font-size:13.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.chat-time { flex-shrink:0; }
.chat-item-bottom { display:flex; justify-content:space-between; gap:8px; margin-top:2px; }
.chat-preview { font-size:12.5px; color:#5b6b60; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.badge { background:#27b95a; color:#fff; font-size:11px; font-weight:800; border-radius:10px; padding:1px 7px; flex-shrink:0; }
.chat-window { flex:1; display:flex; flex-direction:column; min-width:0; background:#eef3ee; }
.chat-head { display:flex; align-items:center; justify-content:space-between; padding:10px 16px; background:#fff; border-bottom:1px solid #e7ece8; }
.chat-head-name { font-weight:800; font-size:14.5px; }
.chat-messages { flex:1; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:6px; }
.day-divider { text-align:center; margin:10px 0 6px; }
.day-divider span { background:#dfe8df; color:#5b6b60; font-size:11px; font-weight:700; padding:3px 10px; border-radius:10px; }
.msg-row { display:flex; }
.msg-row.mine { justify-content:flex-end; }
.msg-row.theirs { justify-content:flex-start; }
.bubble { max-width:70%; padding:8px 12px; border-radius:14px; font-size:13.5px; line-height:1.45; position:relative; word-wrap:break-word; white-space:pre-wrap; }
.msg-row.theirs .bubble { background:#fff; border:1px solid #e2e8e0; border-bottom-left-radius:4px; }
.msg-row.mine .bubble { background:#d6f5df; border:1px solid #c0ecd0; border-bottom-right-radius:4px; }
.bubble.failed { border-color:#f3bcbc; background:#fdf1f1; }
.bubble-text { white-space:pre-wrap; }
.bubble-meta { display:flex; justify-content:flex-end; gap:4px; font-size:10.5px; color:#7a8a80; margin-top:2px; }
.chat-input { background:#fff; border-top:1px solid #e7ece8; padding:10px 0 12px; }
.chat-input-row { display:flex; gap:10px; align-items:flex-end; padding:0 14px; }
.chat-textarea { flex:1; resize:none; max-height:140px; }
.send-btn { height:40px; width:48px; font-size:16px; flex-shrink:0; }
.chat-empty { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; color:#5b6b60; text-align:center; padding:30px; }
@media (max-width: 900px) { .messenger { flex-direction:column; height:auto; } .chat-side { width:100%; max-height:280px; } }
</style>
