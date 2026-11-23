<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { apiState, commsApi } from '@/api/commsClient';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import WhatsAppTemplateSender from '@/components/WhatsAppTemplateSender.vue';
import CommsInboxWork from '@/components/CommsInboxWork.vue';
import { INBOX_STATES, isResponseOverdue } from '@/data/commsInbox';

const db = useDbStore();
const ui = useUiStore();

const online = ref(apiState.online);
const inboxFilter = ref('active');
const inboxStaff = ref({ items: [], login: '', canAssignOthers: false });

async function loadInboxStaff() {
  try { inboxStaff.value = await commsApi.assignees(); }
  catch { /* доступность списка сотрудников не блокирует переписку */ }
}

function applyInboxWork(key, work) {
  const chat = chatList.value.find((row) => row.key === key);
  if (chat) chat.work = work;
}

async function applySavedClient(key, { client, work }) {
  ++loadVersion;
  const chat = chatList.value.find((row) => row.key === key);
  if (chat) {
    chat.farmId = client.id;
    chat.work = work;
    for (const message of chat.messages || []) message.farmId = client.id;
  }
  await Promise.allSettled([db.pullCrmState(), db.syncComms(true)]);
  if (activeKey.value === key) await loadChats(true, key);
}

// фильтр сети (канала) прямо в списке чатов
const chatKindFilter = ref(localStorage.getItem('biotorf_chat_kind') || 'all');
function setChatKind(k) { chatKindFilter.value = k; localStorage.setItem('biotorf_chat_kind', k); }

// ── состояние чатов (как в Telegram) ─────────────────────────────
const chatList = ref([]);          // [{key,kind,farmId,contact,phone,handle,unread,lastMessage,draft,messages}]
const activeKey = ref(null);       // открытый диалог
const chatInput = ref('');
const chatSending = ref(false);
const chatError = ref('');
const chatNotice = ref('');
const newChatOpen = ref(false);
const templateMode = ref(false);
const newChat = ref({ kind: 'telegram', handle: '', phone: '', contact: '', text: '' });
const newChatError = ref('');

// ── динамические каналы (реестр бэкенда: Instagram, VK, Авито и т.д.) ──
import { channelsApi } from '../api/channelsClient';
import ManualLink from '@/components/ui/ManualLink.vue';
const dynChannels = ref([]);            // [{id,label,icon,color,connected}]
async function loadChannels() {
  if (!online.value) return;
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
let firstLoad = true;
let loadVersion = 0;
const drafts = new Map();

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
// чат может вестись в нескольких сетях (например, клиент пишет и в ТГ, и в WhatsApp)
function chatKinds(c) {
  const set = new Set([c.kind]);
  for (const m of c.messages || []) if (m.kind) set.add(m.kind);
  return [...set];
}
const sortedChats = computed(() =>
  [...chatList.value].sort((a, b) => (a.lastTs < b.lastTs ? 1 : -1))
    .filter((c) => {
      if (chatKindFilter.value !== 'all' && !chatKinds(c).includes(chatKindFilter.value)) return false;
      const state = c.work?.state;
      if (inboxFilter.value === 'active' && state === 'closed') return false;
      if (inboxFilter.value === 'closed' && state !== 'closed') return false;
      if (inboxFilter.value === 'mine' && (state === 'closed' || !c.work?.assignee || c.work.assignee !== inboxStaff.value.login)) return false;
      if (inboxFilter.value === 'overdue' && !isResponseOverdue(c.work)) return false;
      const q = ui.search.toLowerCase();
      if (!q) return true;
      return [peerTitle(c), c.contact, c.handle, c.phone, c.lastMessage?.text]
        .filter(Boolean).join(' ').toLowerCase().includes(q);
    })
);
const totalUnread = computed(() => chatList.value.reduce((s, c) => s + (c.unread || 0), 0));
// сообщения открытого диалога: все или только выбранной сети (переключатель в шапке чата)
const chatMessages = computed(() => {
  const msgs = (activeChat.value?.messages || []).slice(-300);
  if (!activeChat.value) return [];
  const kinds = chatKinds(activeChat.value);
  if (msgKindFilter.value !== 'all' && kinds.includes(msgKindFilter.value)) {
    return msgs.filter((m) => m.kind === msgKindFilter.value);
  }
  return msgs;
});
const msgKindFilter = ref('all');
watch(activeKey, () => { msgKindFilter.value = 'all'; });

function localChats() {
  const grouped = new Map();
  for (const item of db.comms || []) {
    const key = item.peerKey || `entry:${item.id}`;
    const chat = grouped.get(key) || { key, messages: [], unread: 0 };
    chat.messages.push(item);
    if (item.dir === 'in' && !item.read) chat.unread++;
    grouped.set(key, chat);
  }
  return [...grouped.values()].map((chat) => {
    chat.messages.sort((a, b) => a.ts.localeCompare(b.ts));
    const last = chat.messages.at(-1);
    return { ...last, ...chat, lastMessage: last, lastTs: last.ts };
  });
}

async function loadChats(quiet = false, focusKey = null) {
  const version = ++loadVersion;
  let rows;
  try {
    rows = online.value ? (await commsApi.chats(200, inboxFilter.value)).items || [] : localChats();
    if (online.value) rows.push(...localChats().filter((c) => c.id?.startsWith('C-local-')));
    if (online.value && focusKey && !rows.some((row) => row.key === focusKey)) {
      try { rows.unshift(await commsApi.chat(focusKey)); }
      catch { /* чат мог исчезнуть после удаления последней записи */ }
    }
  } catch (e) {
    if (!quiet && version === loadVersion) chatError.value = e.message || 'Не удалось загрузить чаты';
    return;
  }
  if (version !== loadVersion) return;
  const oldLast = activeChat.value?.lastMessage?.id;
  chatList.value = rows;
  if (focusKey && activeKey.value !== focusKey) {
    const target = rows.find((c) => c.key === focusKey);
    if (target) openChat(target, false);
  } else if (firstLoad && !activeKey.value && rows.length) {
    const focused = ui.commsFocusFarm && rows.find((c) => c.farmId === ui.commsFocusFarm);
    openChat(focused || rows.find((c) => c.unread > 0) || rows[0], false);
  } else if (oldLast !== activeChat.value?.lastMessage?.id && msgBox.value &&
    msgBox.value.scrollHeight - msgBox.value.scrollTop - msgBox.value.clientHeight < 100) {
    scrollBottom();
  }
  firstLoad = false;
}

function draftKey(key) {
  return `biotorf.comms.draft:${ui.login || 'local'}:${key}`;
}

function setDraft(key, value) {
  drafts.set(key, value);
  try {
    if (value) localStorage.setItem(draftKey(key), value);
    else localStorage.removeItem(draftKey(key));
  } catch { /* черновик остаётся в памяти вкладки */ }
}

function getDraft(key) {
  if (drafts.has(key)) return drafts.get(key);
  try { return localStorage.getItem(draftKey(key)) || ''; }
  catch { return ''; }
}

async function openChat(chat, doRead = true) {
  if (activeKey.value !== chat.key) {
    activeKey.value = chat.key;
    sendKind.value = '';
    chatInput.value = getDraft(chat.key);
    chatError.value = '';
    chatNotice.value = '';
  }
  if (doRead && chat.unread) {
    try {
      if (online.value) await commsApi.markChatRead(chat.key);
      for (const entry of db.comms || []) {
        if ((entry.peerKey || `entry:${entry.id}`) === chat.key && entry.dir === 'in') entry.read = true;
      }
      for (const entry of chat.messages || []) if (entry.dir === 'in') entry.read = true;
      chat.unread = 0;
      db.save('Прочитан диалог', chat.key, false);
    } catch (error) { chatError.value = error.message; }
  }
  scrollBottom();
}

async function readAllChats() {
  if (!totalUnread.value) return;
  try {
    if (online.value) await commsApi.readAll();
    for (const item of db.comms || []) item.read = true;
    for (const chat of chatList.value) {
      chat.unread = 0;
      for (const item of chat.messages || []) item.read = true;
    }
    db.save('Отмечены прочитанными все сообщения', 'Коммуникации', false);
  } catch (error) { chatError.value = error.message; }
}

const msgBox = ref(null);
function scrollBottom() {
  requestAnimationFrame(() => {
    if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight;
  });
}

function replyable(message) {
  if (!message || message.kind === 'call' || message.source === 'manual') return false;
  if (message.dir === 'out' && !['chat', 'reply'].includes(message.source)) return false;
  if (message.kind === 'telegram') return !!(message.payload?.chatId || message.payload?.userIndex);
  if (message.kind === 'whatsapp') return !!message.phone;
  return !!(message.handle || message.phone || message.payload);
}

const sendKinds = computed(() =>
  [...new Set((activeChat.value?.messages || []).filter(replyable).map((m) => m.kind))],
);
const sendKind = ref('');
watch(sendKinds, (available) => {
  if (available.includes(sendKind.value)) return;
  const lastInbound = [...(activeChat.value?.messages || [])].reverse().find((m) => m.dir === 'in' && replyable(m));
  sendKind.value = lastInbound?.kind || available.at(-1) || '';
}, { immediate: true });

function sendFeedback(result) {
  if (result.error) chatError.value = result.error;
  else {
    chatNotice.value = result.sent ? 'Сообщение передано в канал.' : 'Сообщение поставлено в очередь.';
  }
}

async function sendChat() {
  const key = activeKey.value;
  const kind = sendKind.value;
  const text = chatInput.value.trim();
  if (!online.value || !key || !kind || !text || chatSending.value) return;
  chatSending.value = true;
  chatError.value = '';
  chatNotice.value = '';
  try {
    const result = await commsApi.sendToChat(key, text, kind);
    setDraft(key, result.error ? text : '');
    await loadChats(true);
    if (activeKey.value === key) {
      if (!result.error) chatInput.value = '';
      sendFeedback(result);
      scrollBottom();
    }
  } catch (e) {
    if (activeKey.value === key) chatError.value = e.message || 'Сервер отклонил отправку';
  } finally {
    chatSending.value = false;
  }
}

function onInput() {
  if (activeKey.value) setDraft(activeKey.value, chatInput.value);
}

const HANDLE_KINDS = ['telegram', 'instagram', 'facebook', 'vk', 'ok'];

async function startNewChat() {
  if (!online.value || chatSending.value) return;
  const f = newChat.value;
  const byPhone = !HANDLE_KINDS.includes(f.kind);
  const target = (byPhone ? f.phone : f.handle).trim();
  const message = f.text.trim();
  newChatError.value = '';
  if (!target || !message) {
    newChatError.value = 'Укажите получателя и текст сообщения.';
    return;
  }
  chatSending.value = true;
  try {
    const result = await commsApi.startChat({
      kind: f.kind,
      contact: f.contact.trim() || null,
      phone: byPhone ? target : null,
      handle: !byPhone ? target : null,
      text: message,
    });
    if (result.item?.peerKey) await loadChats(true, result.item.peerKey);
    if (result.error) {
      newChatError.value = result.error;
    } else {
      newChatOpen.value = false;
      f.text = '';
      sendFeedback(result);
    }
  } catch (error) {
    newChatError.value = error.message || 'Не удалось начать диалог';
  } finally {
    chatSending.value = false;
  }
}

function whatsappAddress(chat) {
  return (chat.messages || []).findLast((message) => message.kind === 'whatsapp' && message.phone)
    || (chat.kind === 'whatsapp' && chat.phone ? chat : null);
}

function showWhatsAppTemplate(chat) {
  const address = whatsappAddress(chat);
  if (!address) return;
  newChat.value = { kind: 'whatsapp', phone: address.phone, contact: address.contact || '', handle: '', text: '' };
  newChatError.value = '';
  newChatOpen.value = true;
  templateMode.value = true;
}

async function templateResult(result) {
  if (result.item?.peerKey) await loadChats(true, result.item.peerKey);
  if (result.sent) {
    newChatOpen.value = false;
    templateMode.value = false;
    sendFeedback(result);
  }
}

function deliveryLabel(status) {
  return ({
    'Отправлено': 'Принято каналом',
    'Передано WhatsApp': 'Передано WhatsApp',
    'Доставлено': 'Доставлено',
    'Прочитано': 'Прочитано',
    'В очереди': 'В очереди',
    'Ошибка доставки': 'Ошибка доставки',
  })[status] || '';
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

const formBusy = ref(false);
const formError = ref('');

async function saveComm() {
  if (formBusy.value) return;
  const f = form.value;
  formError.value = '';
  if (f.kind !== 'call' && !f.text.trim()) {
    formError.value = 'Введите текст для журнала.';
    return;
  }
  if (!f.farmId && !f.phone.trim() && !f.handle.trim() && !f.contact.trim()) {
    formError.value = 'Укажите клиента, контакт или номер.';
    return;
  }
  formBusy.value = true;
  try {
    await db.addComm({
      kind: f.kind,
      dir: f.dir,
      farmId: f.farmId || null,
      contact: f.contact.trim() || null,
      phone: HANDLE_KINDS.includes(f.kind) ? null : (f.phone.trim() || null),
      handle: HANDLE_KINDS.includes(f.kind) ? (f.handle.trim() || null) : null,
      ...(f.kind === 'call'
        ? { status: f.status, duration: Math.max(0, Number(f.durationMin) || 0) * 60, note: f.note.trim() }
        : { text: f.text.trim() }),
      read: true,
    });
    showForm.value = false;
    f.text = '';
    f.note = '';
    await loadChats();
  } catch (error) { formError.value = error.message; }
  finally { formBusy.value = false; }
}

// ── автообновление ленты: входящие сообщения и статусы доставки ответов
// подтягиваются с сервера сами, без ручного F5 ──────────────────────
const autoRefresh = ref(true);
let pollTimer = null;

let polling = false;
let mounted = true;
watch(inboxFilter, () => loadChats(false, activeKey.value));
async function tick() {
  if (!mounted || !autoRefresh.value || document.hidden || polling) return;
  polling = true;
  try {
    const wasOnline = online.value;
    await db.syncComms(true);
    if (!mounted) return;
    online.value = apiState.online;
    if (!wasOnline && online.value) await Promise.all([loadChannels(), loadInboxStaff()]);
    await loadChats(true, activeKey.value);
  } finally { polling = false; }
}

onMounted(async () => {
  await db.syncComms();
  if (!mounted) return;
  online.value = apiState.online;
  if (online.value) await Promise.all([loadChannels(), loadInboxStaff()]);
  await loadChats();
  if (!mounted) return;
  pollTimer = setInterval(tick, 4000);
  window.addEventListener('focus', tick);
  if (ui.commsFocusFarm) {
    ui.search = db.farmById(ui.commsFocusFarm)?.name || '';
    ui.commsFocusFarm = null;
  }
});

onBeforeUnmount(() => {
  mounted = false;
  loadVersion++;
  clearInterval(pollTimer);
  window.removeEventListener('focus', tick);
});
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Коммуникации</h1>
        <ManualLink />
        <div class="subtitle">Единая лента: звонки с телефона, Telegram и WhatsApp. Всё общение с клиентом — внутри сервиса.</div>
      <BackendBadge collection="comms" />
      </div>
      <div class="actionbar">
        <label class="mini" style="display:flex;align-items:center;gap:6px;cursor:pointer" title="Лента и статусы доставки подтягиваются с сервера каждые 4 секунды">
          <input type="checkbox" v-model="autoRefresh" /> автообновление
        </label>
        <button class="btn slim ghost" @click="readAllChats" :disabled="!totalUnread">
          Прочитано всё ({{ totalUnread }})
        </button>
        <button class="btn primary" @click="showForm = !showForm">＋ Зафиксировать</button>
      </div>
    </div>

    <div class="note">
      <template v-if="online">Журнал синхронизируется с общей базой. Ответы отправляются из диалога.</template>
      <template v-else>Сервер недоступен. Показаны данные этого браузера, отправка сообщений недоступна.</template>
      <div v-if="db.commsSyncError" class="comms-error">Ошибка синхронизации: {{ db.commsSyncError }}</div>
    </div>
    <p v-if="chatError && !activeChat" class="comms-error" role="alert">{{ chatError }}</p>

    <div v-if="showForm" class="panel" style="margin-bottom:18px">
      <div class="panel-head"><span class="panel-title">Запись в журнале</span></div>
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
      <p v-if="formError" class="comms-error" role="alert">{{ formError }}</p>
      <div class="modal-foot" style="padding:14px 0 0;border-top:0">
        <button class="btn ghost" @click="showForm = false">Отмена</button>
        <button class="btn primary" :disabled="formBusy" @click="saveComm">Записать в журнал</button>
      </div>
    </div>

    <div class="messenger">
        <aside class="chat-side">
          <div class="chat-side-head" data-tour="inbox-queue">
            <span class="panel-title">Чаты</span>
            <button v-if="online" class="btn slim primary" @click="newChatOpen = !newChatOpen; templateMode = false">＋ Диалог</button>
          </div>
          <div v-if="online" class="chat-kind-filter">
            <select v-model="inboxFilter" aria-label="Очередь диалогов" class="select">
              <option value="active">Активные</option>
              <option value="mine">Мои диалоги</option>
              <option value="overdue">Просроченные</option>
              <option value="closed">Закрытые</option>
              <option value="all">Все диалоги</option>
            </select>
          </div>
          <div class="chat-kind-filter">
            <button class="chip mini-chip" :class="{ selected: chatKindFilter === 'all' }"
                    :style="chatKindFilter === 'all' ? 'background:#27b95a;color:#fff' : ''"
                    @click="setChatKind('all')">Все</button>
            <button v-for="[key, label] in BASE_FILTERS.filter(([k]) => k !== 'all')" :key="key"
                    class="chip mini-chip" :class="{ selected: chatKindFilter === key }"
                    :style="chatKindFilter === key ? 'background:#27b95a;color:#fff' : ''"
                    @click="setChatKind(key)">{{ label }}</button>
            <button v-for="ch in dynChannels" :key="ch.id"
                    class="chip mini-chip" :class="{ selected: chatKindFilter === ch.id }"
                    :style="chatKindFilter === ch.id ? 'background:#27b95a;color:#fff' : ''"
                    @click="setChatKind(ch.id)">{{ ch.icon }} {{ ch.label }}</button>
          </div>
          <div v-if="online && newChatOpen" class="newchat">
            <select v-model="newChat.kind" class="select" @change="templateMode = false">
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
            <button v-if="newChat.kind === 'whatsapp'" class="btn slim" @click="templateMode = !templateMode">
              {{ templateMode ? 'Обычное сообщение' : 'Шаблон WhatsApp' }}
            </button>
            <WhatsAppTemplateSender v-if="templateMode" :phone="newChat.phone" :contact="newChat.contact" @result="templateResult" />
            <template v-else>
              <textarea v-model="newChat.text" class="textarea" rows="2" maxlength="4000" placeholder="Первое сообщение…"></textarea>
              <p v-if="newChatError" class="comms-error" role="alert">{{ newChatError }}</p>
              <button class="btn primary slim" :disabled="chatSending" @click="startNewChat">Начать диалог</button>
            </template>
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
                  <span class="chat-preview">{{ c.lastMessage?.dir === 'out' ? '→ ' : '' }}{{ (c.lastMessage?.text || c.lastMessage?.note || c.lastMessage?.status || '').slice(0, 60) }}</span>
                  <span v-if="c.unread" class="badge">{{ c.unread }}</span>
                </div>
                <span v-if="c.work" class="mini" :class="{ 'comms-error': isResponseOverdue(c.work) }">
                  {{ isResponseOverdue(c.work) ? 'Просрочен ответ' : INBOX_STATES[c.work.state] }}
                </span>
              </div>
            </div>
            <div v-if="!sortedChats.length" class="empty" style="padding:18px">Диалогов пока нет.</div>
          </div>
        </aside>

        <section class="chat-window">
          <template v-if="activeChat">
            <header class="chat-head">
              <div>
                <div class="chat-head-name">
                  {{ peerTitle(activeChat) }}
                </div>
                <div class="mini">{{ channelMeta[activeChat.kind]?.label || activeChat.kind }} · {{ peerSub(activeChat) || 'диалог' }}</div>
              </div>
              <!-- выбор сети, в которую идёт ответ (если диалог ведётся в нескольких) -->
              <select v-if="chatKinds(activeChat).length > 1" v-model="msgKindFilter" class="select kind-select" title="Показать сообщения канала">
                <option value="all">Все сети</option>
                <option v-for="k in chatKinds(activeChat)" :key="k" :value="k">{{ channelMeta[k]?.icon || '💬' }} {{ channelMeta[k]?.label || k }}</option>
              </select>
              <button v-if="online && whatsappAddress(activeChat)" class="btn slim"
                      @click="showWhatsAppTemplate(activeChat)">Шаблон WhatsApp</button>
              <span v-if="deliveryLabel(activeChat.lastOutStatus)" class="pill"
                    :class="activeChat.lastOutStatus === 'Ошибка доставки' ? 'red' : activeChat.lastOutStatus === 'В очереди' ? 'amber' : 'green'">
                {{ deliveryLabel(activeChat.lastOutStatus) }}
              </span>
            </header>
            <CommsInboxWork v-if="online && activeChat.work" :key="activeChat.key" :chat="activeChat"
                            :staff="inboxStaff" @updated="applyInboxWork" @client-saved="applySavedClient" />
            <div ref="msgBox" class="chat-messages">
              <template v-for="(m, i) in chatMessages" :key="m.seq ?? m.id">
                <div v-if="dayGap(chatMessages, i)" class="day-divider"><span>{{ fmtDay(m.ts) }}</span></div>
                <div class="msg-row" :class="m.dir === 'out' ? 'mine' : 'theirs'">
                  <div class="bubble" :class="['k-' + m.kind, { failed: m.status === 'Ошибка доставки' }]">
                    <div class="bubble-text">{{ m.text || (m.kind === 'call' ? `Звонок · ${m.status || ''}` : '') }}</div>
                    <div v-if="m.kind === 'call' && m.note" class="bubble-text">{{ m.note }}</div>
                    <div v-if="m.kind === 'call' && m.duration" class="mini">{{ Math.round(m.duration / 60) }} мин</div>
                    <div v-if="m.source === 'manual' && m.kind !== 'call'" class="mini">Запись в журнале</div>
                    <div v-if="m.payload?.sendError && m.status === 'Ошибка доставки'" class="mini comms-error">{{ m.payload.sendError }}</div>
                    <div class="bubble-meta">
                      <span>{{ fmtTime(m.ts) }}</span>
                      <span v-if="m.dir === 'out'">{{ deliveryLabel(m.status) }}</span>
                    </div>
                  </div>
                </div>
              </template>
              <div v-if="!chatMessages.length" class="empty" style="padding:24px">Сообщений нет — напишите первым.</div>
            </div>
            <footer class="chat-input">
              <div v-if="chatError" class="mini comms-error" style="padding:0 14px">{{ chatError }}</div>
              <div v-if="chatNotice" class="mini comms-ok" style="padding:0 14px">{{ chatNotice }}</div>
              <div v-if="online && sendKinds.length" class="chat-input-row">
                <!-- явная выбор сети, из которой идёт сообщение -->
                <select v-model="sendKind" class="select kind-select send-kind" title="Сеть отправки">
                  <option v-for="k in sendKinds" :key="k" :value="k">{{ channelMeta[k]?.icon || '💬' }} {{ channelMeta[k]?.label || k }}</option>
                </select>
                <textarea
                  v-model="chatInput" class="textarea chat-textarea" rows="1"
                  maxlength="4000"
                  placeholder="Сообщение… (Enter — отправить)"
                  @input="onInput"
                  @keydown.enter.exact.prevent="sendChat"
                ></textarea>
                <button class="btn primary send-btn" :disabled="!sendKind || !chatInput.trim() || chatSending" @click="sendChat">
                  {{ chatSending ? '…' : '➤' }}
                </button>
              </div>
              <p v-else class="mini">В этом диалоге пока нет доступного канала для ответа.</p>
            </footer>
          </template>
          <div v-else class="chat-empty">
            <div style="font-size:40px">💬</div>
            <div>Выберите чат слева или начните новый диалог</div>
            <div class="mini">Входящие из Telegram и WhatsApp автоматически группируются в чаты по собеседнику</div>
          </div>
        </section>
    </div>


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
.chat-kind-filter { display:flex; flex-wrap:wrap; gap:6px; padding:10px 12px; border-bottom:1px solid #e7ece8; background:#fff; }
.mini-chip { font-size:11.5px; padding:3px 9px; border-radius:9px; border:1px solid #dfe7df; background:#f6f9f6; cursor:pointer; }
.mini-chip.selected { border-color:#27b95a; }
.kind-select { width:auto; min-width:150px; font-size:12.5px; padding:6px 8px; }
.send-kind { flex-shrink:0; align-self:flex-end; }
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
