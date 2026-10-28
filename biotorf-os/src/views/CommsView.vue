<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { apiState, COMMS_API_URL, caps, commsApi } from '@/api/commsClient';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const ui = useUiStore();

// ── режим страницы: только мессенджер (лента «все сообщения» убрана по требованию) ──
const MODE_KEY = 'biotorf_comms_mode';
const mode = ref('chats');
localStorage.setItem(MODE_KEY, 'chats');
function setMode(m) { mode.value = m; localStorage.setItem(MODE_KEY, m); }

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
    // сеть ответа: выбранная в шапке чата, либо канал последнего входящего сообщения
    let kind = msgKindFilter.value !== 'all' ? msgKindFilter.value : null;
    if (!kind) {
      const lastIn = [...(c.messages || [])].reverse().find((m) => m.dir === 'in' && m.kind !== 'call');
      kind = lastIn?.kind || c.kind || null;
    }
    const res = await commsApi.sendToChat(c.key, text, kind);
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
        <button class="btn slim ghost" @click="db.markAllCommsRead()" :disabled="!totalUnread">
          Прочитано всё ({{ totalUnread }})
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
      <button class="chip selected" style="background:#27b95a;color:#fff" @click="setMode('chats')">
        💬 Чаты<template v-if="totalUnread"> · {{ totalUnread }}</template>
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
              <!-- выбор сети, в которую идёт ответ (если диалог ведётся в нескольких) -->
              <select v-if="chatKinds(activeChat).length > 1" v-model="msgKindFilter" class="select kind-select" title="Сеть для ответа">
                <option value="all">Все сети</option>
                <option v-for="k in chatKinds(activeChat)" :key="k" :value="k">{{ channelMeta[k]?.icon || '💬' }} {{ channelMeta[k]?.label || k }}</option>
              </select>
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
                <!-- явная выбор сети, из которой идёт сообщение -->
                <select v-model="msgKindFilter" class="select kind-select send-kind" title="Сеть отправки">
                  <option v-for="k in chatKinds(activeChat)" :key="k" :value="k">{{ channelMeta[k]?.icon || '💬' }} {{ channelMeta[k]?.label || k }}</option>
                  <template v-if="chatKinds(activeChat).length > 1"><option value="all">Авто (последняя входящая)</option></template>
                </select>
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
