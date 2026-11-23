<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { apiState, checkApi, commsApi } from '@/api/commsClient';
import { channelsApi } from '@/api/channelsClient';
import ChannelIcon from '@/components/ChannelIcon.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
import WhatsAppTemplateSender from '@/components/WhatsAppTemplateSender.vue';
import CommsInboxWork from '@/components/CommsInboxWork.vue';
import { INBOX_STATES, isResponseOverdue } from '@/data/commsInbox';

const db = useDbStore();
const ui = useUiStore();
const { canEdit, canSeeFarm } = usePermissions();
const trainingActive = inject('trainingActive', ref(false));
const online = ref(apiState.online);
const inboxFilter = ref('active');
const inboxQuery = ref('');
const inboxStaff = ref({ items: [], login: '', canAssignOthers: false });
const capabilities = ref(null);
const visibleFarms = computed(() => db.farms.filter(canSeeFarm));
const canWriteComms = computed(() => canEdit('comms') && capabilities.value?.canSend !== false);

const KIND_META = {
  call: { label: 'Звонок' },
  telegram: { label: 'Telegram' },
  whatsapp: { label: 'WhatsApp' },
  email: { label: 'Email' },
  instagram: { label: 'Instagram' },
  facebook: { label: 'Messenger' },
  vk: { label: 'ВКонтакте' },
  ok: { label: 'Одноклассники' },
  avito: { label: 'Авито' },
  youdo: { label: 'YouDo' },
};
const BASE_FILTERS = [['all', 'Все'], ['call', 'Звонки'], ['telegram', 'Telegram'], ['whatsapp', 'WhatsApp']];
const HANDLE_KINDS = ['telegram', 'instagram', 'facebook', 'vk', 'ok', 'email', 'avito', 'youdo'];
const channels = ref([]);
const dynChannels = computed(() => channels.value.filter(({ id, enabled }) =>
  enabled && !BASE_FILTERS.some(([kind]) => kind === id)));
const channelMeta = computed(() => Object.fromEntries([
  ...Object.entries(KIND_META), ...channels.value.map((record) => [record.id, record]),
]));

function channelAvailability(kind) {
  const status = capabilities.value?.channelStatuses?.[kind];
  const record = channels.value.find(({ id }) => id === kind);
  if (kind === 'call') {
    return { state: 'archive', label: 'Журнал звонков', description: 'Сюда попадают звонки. Результат можно записать в журнал.', canSend: false };
  }
  if (!online.value) return { state: 'offline', label: 'Нет связи', description: 'Дождитесь подключения к серверу CRM.', canSend: false };
  if (status?.mode === 'disabled' || record?.enabled === false) {
    return { state: 'disabled', label: 'Отключён', description: 'Канал выключен. Руководитель может включить его в настройках каналов.', canSend: false };
  }
  if (!capabilities.value) {
    return { state: 'loading', label: 'Статус неизвестен', description: 'Не удалось проверить отправку. Обновите входящие.', canSend: false };
  }
  const direct = status?.mode === 'direct' || (!status &&
    ((kind === 'telegram' && capabilities.value.telegramSend) || (kind === 'whatsapp' && capabilities.value.whatsappSend)));
  if (direct) return { state: 'direct', label: 'Настроен', description: 'Отправка из CRM доступна.', canSend: canWriteComms.value };
  if (status?.mode === 'queue') {
    return { state: 'queue', label: 'Через очередь', description: 'Сообщение попадёт в очередь коннектора. Статус доставки появится в диалоге.', canSend: canWriteComms.value };
  }
  return {
    state: 'archive',
    label: status?.inbound ? 'Только входящие' : 'Только журнал',
    description: status?.reason || 'Отправка для этого канала пока не настроена. Сообщения можно фиксировать в журнале.',
    canSend: false,
  };
}

const canUseWhatsAppTemplates = computed(() => channelAvailability('whatsapp').canSend &&
  (capabilities.value?.whatsappTemplates ?? capabilities.value?.whatsappSend ?? false));
const newChatKinds = computed(() => ['telegram', 'whatsapp', ...dynChannels.value.map(({ id }) => id)]);
const newChatOpen = ref(false);
const newChat = ref(newChatForm());
const newChatError = ref('');
const newChatAvailability = computed(() => {
  const availability = channelAvailability(newChat.value.kind);
  if (newChat.value.kind !== 'whatsapp' || !availability.canSend) return availability;
  return {
    ...availability,
    canSend: false,
    description: canUseWhatsAppTemplates.value
      ? 'Для начала разговора выберите одобренный шаблон WhatsApp.'
      : 'Чтобы начать разговор, руководителю нужно настроить одобренные шаблоны WhatsApp.',
  };
});

function newChatForm(kind = 'telegram') { return { kind, handle: '', phone: '', contact: '', text: '' }; }

function onNewChatKindChange() {
  newChat.value = { ...newChatForm(newChat.value.kind), text: newChat.value.text };
  newChatError.value = '';
}

function closeNewChat() {
  if (!chatSending.value) newChatOpen.value = false;
}

function toggleNewChat() {
  if (newChatOpen.value) return closeNewChat();
  const kind = newChatKinds.value.find((channel) => channel === 'whatsapp'
    ? canUseWhatsAppTemplates.value : channelAvailability(channel).canSend);
  newChat.value = newChatForm(kind);
  newChatError.value = '';
  newChatOpen.value = true;
}

watch(newChatOpen, async (open) => {
  if (!open) return;
  await nextTick();
  document.getElementById('new-comms-dialog')?.scrollIntoView({ block: 'nearest' });
});

function recipientMeta(kind) {
  if (kind === 'telegram') return { field: 'handle', type: 'text', label: 'Имя пользователя Telegram', placeholder: '@username' };
  if (kind === 'email') return { field: 'handle', type: 'email', label: 'Электронная почта', placeholder: 'name@example.com' };
  if (HANDLE_KINDS.includes(kind)) return { field: 'handle', type: 'text', label: 'Логин или ID получателя', placeholder: 'Логин или ID' };
  return { field: 'phone', type: 'tel', label: 'Номер телефона получателя', placeholder: '+996 …' };
}

let settingsVersion = 0;
let lastSettingsCheck = 0;
let settingsRequest;
async function loadSettings() {
  if (settingsRequest) return settingsRequest;
  const version = ++settingsVersion;
  settingsRequest = Promise.allSettled([channelsApi.list(), commsApi.capabilities(), commsApi.assignees()])
    .then(([registry, caps, staff]) => {
      if (!mounted || settingsVersion !== version) return;
      if (registry.status === 'fulfilled') channels.value = registry.value.items || [];
      if (caps.status === 'fulfilled') capabilities.value = caps.value;
      if (staff.status === 'fulfilled') inboxStaff.value = staff.value;
      lastSettingsCheck = Date.now();
    })
    .finally(() => { settingsRequest = null; });
  return settingsRequest;
}

function storedChannel() {
  try { return localStorage.getItem('biotorf_chat_kind') || 'all'; }
  catch { return 'all'; }
}
const chatKindFilter = ref(storedChannel());
function setChatKind(kind) {
  chatKindFilter.value = kind;
  try { localStorage.setItem('biotorf_chat_kind', kind); } catch { /* фильтр действует в этой вкладке */ }
}
watch(dynChannels, () => {
  if (![...BASE_FILTERS.map(([kind]) => kind), ...dynChannels.value.map(({ id }) => id)].includes(chatKindFilter.value)) {
    setChatKind('all');
  }
});

const chatList = ref([]);
const activeKey = ref(null);
const chatInput = ref('');
const chatSending = ref(false);
const chatError = ref('');
const chatNotice = ref('');
const loadingChats = ref(true);
const loadingThread = ref(false);
const loadError = ref('');
const threadError = ref('');
const activeChat = computed(() => chatList.value.find(({ key }) => key === activeKey.value) || null);
const msgKindFilter = ref('all');
const msgBox = ref(null);
const inboxHeading = ref(null);
const drafts = new Map();
let listController;
let detailController;
let detailKey;
let firstLoad = true;
let readThreadKey = null;
let mounted = true;
const markingRead = new Set();
let markingAll = false;

function peerTitle(chat) {
  const name = chat.farmId && db.farmById(chat.farmId)?.name;
  return name || chat.contact || chat.handle || chat.phone || chat.farmId || 'Неизвестный контакт';
}
function peerSub(chat) {
  return [...new Set([chat.contact, chat.handle, chat.phone].filter((part) => part && part !== peerTitle(chat)))].join(' · ');
}

function fmtDay(iso) {
  const date = new Date(iso);
  if (!iso || Number.isNaN(date.valueOf())) return 'Дата неизвестна';
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return 'Сегодня';
  today.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return 'Вчера';
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}
function fmtTime(iso) {
  const date = new Date(iso);
  return iso && !Number.isNaN(date.valueOf())
    ? date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '';
}
function dayGap(list, index) {
  return index === 0 || fmtDay(list[index].ts) !== fmtDay(list[index - 1].ts);
}

const lower = (value) => String(value || '').trim().toLocaleLowerCase('ru').replaceAll('ё', 'е');
const digits = (value) => String(value || '').replace(/\D/g, '');
function matchesQuery(chat) {
  const query = lower(inboxQuery.value);
  if (!query) return true;
  const address = digits(query);
  return [peerTitle(chat), chat.contact, chat.handle, chat.phone, chat.lastMessage?.text, chat.lastMessage?.note]
    .some((value) => lower(value).includes(query)) ||
    (address.length >= 3 && /^[+\d\s().-]+$/.test(query) && digits(chat.phone).includes(address));
}
function chatKinds(chat) {
  return [...new Set([chat.kind, ...(chat.kinds || []), ...(chat.messages || []).map(({ kind }) => kind)].filter(Boolean))];
}

const sortedChats = computed(() => [...chatList.value]
  .sort((left, right) => String(right.lastTs || '').localeCompare(String(left.lastTs || '')))
  .filter((chat) => {
    if (chatKindFilter.value !== 'all' && !chatKinds(chat).includes(chatKindFilter.value)) return false;
    const state = chat.work?.state;
    if (inboxFilter.value === 'active' && state === 'closed') return false;
    if (inboxFilter.value === 'closed' && state !== 'closed') return false;
    if (inboxFilter.value === 'mine' && (state === 'closed' || !chat.work?.assignee ||
      chat.work.assignee !== (inboxStaff.value.login || ui.login))) return false;
    if (inboxFilter.value === 'overdue' && !isResponseOverdue(chat.work)) return false;
    return matchesQuery(chat);
  }));
const totalUnread = computed(() => chatList.value.reduce((sum, chat) => sum + (Number(chat.unread) || 0), 0));
const chatMessages = computed(() => {
  const thread = activeChat.value?.messages || [];
  return msgKindFilter.value === 'all' ? thread : thread.filter(({ kind }) => kind === msgKindFilter.value);
});

function localChats() {
  const grouped = new Map();
  for (const item of db.comms || []) {
    const key = item.peerKey || `entry:${item.id}`;
    const group = grouped.get(key) || { key, messages: [], unread: 0 };
    group.messages.push(item);
    if (item.dir === 'in' && !item.read) group.unread += 1;
    grouped.set(key, group);
  }
  return [...grouped.values()].map((group) => {
    group.messages.sort((a, b) => String(a.ts || '').localeCompare(String(b.ts || '')));
    const last = group.messages.at(-1);
    return {
      ...last, ...group, lastMessage: last, lastTs: last.ts,
      localOnly: group.messages.every(({ id }) => String(id || '').startsWith('C-local-')),
    };
  });
}

function putConversation(chat) {
  const index = chatList.value.findIndex(({ key }) => key === chat.key);
  if (index < 0) chatList.value.unshift(chat);
  else chatList.value[index] = { ...chatList.value[index], ...chat };
}
function stopListRequest() { listController?.abort(); }
function stopThreadRequest(key) { if (!key || key === detailKey) detailController?.abort(); }
function stopRefresh(key) { stopListRequest(); stopThreadRequest(key); }

function explainRequest(error, fallback) {
  if (error?.name === 'TimeoutError' || error instanceof TypeError) return fallback;
  return error?.message || fallback;
}

async function loadThread(key, quiet = false) {
  if (!online.value || !key || activeChat.value?.localOnly) return activeChat.value;
  stopThreadRequest();
  const request = new AbortController();
  detailController = request;
  detailKey = key;
  loadingThread.value = !quiet;
  const nearEnd = !msgBox.value || msgBox.value.scrollHeight - msgBox.value.scrollTop - msgBox.value.clientHeight < 110;
  const lastShown = activeChat.value?.messages?.at(-1)?.id;
  try {
    const detail = await commsApi.chat(key, { signal: request.signal });
    if (!mounted || request.signal.aborted || activeKey.value !== key) return null;
    putConversation(detail);
    if (!quiet && detail.messages?.length) db.mergeServerComms(detail.messages);
    threadError.value = '';
    if (nearEnd && detail.messages?.at(-1)?.id !== lastShown) scrollBottom();
    return detail;
  } catch (error) {
    if (!request.signal.aborted && activeKey.value === key && (!quiet || !activeChat.value?.messages?.length)) {
      threadError.value = explainRequest(error, 'Не удалось загрузить историю диалога. Обновите входящие.');
    }
    return null;
  } finally {
    if (detailController === request) loadingThread.value = false;
  }
}

async function loadChats(quiet = false, focusKey = null) {
  stopListRequest();
  const request = new AbortController();
  listController = request;
  if (!quiet) loadingChats.value = true;
  try {
    const remote = online.value
      ? (await commsApi.chats(500, 'all', { compact: true, signal: request.signal })).items || [] : [];
    if (!mounted || request.signal.aborted) return false;
    const local = localChats();
    const oldRows = new Map(chatList.value.map((row) => [row.key, row]));
    const rows = online.value ? remote.map((row) => ({
      ...row,
      messages: mergeMessages(oldRows.get(row.key)?.messages, row.messages),
    })) : local.length ? local : [...oldRows.values()];
    if (online.value) {
      const keys = new Set(rows.map(({ key }) => key));
      for (const localRow of local.filter(({ localOnly }) => localOnly)) {
        if (!keys.has(localRow.key)) rows.push(localRow);
      }
      if (activeKey.value && !keys.has(activeKey.value) && !rows.some(({ key }) => key === activeKey.value)) {
        const keep = oldRows.get(activeKey.value);
        if (keep) rows.push(keep);
      }
    }
    chatList.value = rows;
    if (!quiet && remote.length) db.mergeServerComms(remote.map(({ lastMessage }) => lastMessage).filter((message) => message?.id));
    loadError.value = '';
    if (focusKey) {
      await openChat(rows.find(({ key }) => key === focusKey) || { key: focusKey }, false);
    } else if (activeKey.value) {
      const detail = await loadThread(activeKey.value, quiet);
      if (detail && readThreadKey === detail.key) void markThreadRead(detail);
    } else if (firstLoad) {
      const client = ui.commsFocusFarm;
      const focused = client && rows.find(({ farmId }) => String(farmId) === String(client));
      if (client) {
        inboxQuery.value = db.farmById(client)?.name || '';
        ui.commsFocusFarm = null;
      }
      const desktop = !globalThis.matchMedia?.('(max-width: 900px)').matches;
      const target = focused || (desktop && sortedChats.value[0]);
      if (target) await openChat(target, false);
    }
    firstLoad = false;
    return true;
  } catch (error) {
    if (!request.signal.aborted && mounted) {
      loadError.value = explainRequest(error, 'Не удалось обновить входящие. Повторите попытку.');
      if (!chatList.value.length) chatList.value = localChats();
    }
    return false;
  } finally {
    if (listController === request) loadingChats.value = false;
  }
}

function mergeMessages(previous = [], latest = []) {
  const byId = new Map(previous.map((message) => [message.id, message]));
  for (const message of latest) byId.set(message.id, message);
  return [...byId.values()].sort((left, right) => String(left.ts || '').localeCompare(String(right.ts || '')) ||
    (Number(left.seq) || 0) - (Number(right.seq) || 0)).slice(-300);
}

async function refreshChats() {
  loadingChats.value = true;
  const wasOnline = online.value;
  online.value = await checkApi({ force: true });
  if (!mounted) return;
  if (online.value) await Promise.all([loadSettings(), loadChats()]);
  else {
    if (wasOnline) capabilities.value = null;
    await loadChats();
  }
}

function draftKey(key) { return `biotorf.comms.draft:${ui.login || 'local'}:${key}`; }
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
    msgKindFilter.value = 'all';
    chatInput.value = getDraft(chat.key);
    chatError.value = '';
    chatNotice.value = '';
    threadError.value = '';
  }
  readThreadKey = doRead ? chat.key : null;
  const thread = await loadThread(chat.key);
  if (activeKey.value !== chat.key) return;
  scrollBottom();
  if (doRead) void markThreadRead(thread || chat);
}

function closeChat() {
  stopThreadRequest();
  activeKey.value = null;
  readThreadKey = null;
  chatError.value = '';
  chatNotice.value = '';
  threadError.value = '';
  nextTick(() => inboxHeading.value?.focus());
}

function updateRead(key, messageIds, unread) {
  let changed = false;
  for (const entry of db.comms || []) {
    if (messageIds.has(entry.id) && entry.dir === 'in' && !entry.read) {
      entry.read = true;
      changed = true;
    }
  }
  const chat = chatList.value.find((row) => row.key === key);
  if (chat) {
    for (const entry of chat.messages || []) if (messageIds.has(entry.id) && entry.dir === 'in') entry.read = true;
    if (chat.lastMessage?.dir === 'in' && messageIds.has(chat.lastMessage.id)) chat.lastMessage.read = true;
    const visibleUnread = (chat.messages || []).filter(({ dir, read }) => dir === 'in' && !read).length;
    chat.unread = Math.max(visibleUnread, (Number(chat.unread) || 0) - unread);
  }
  if (changed) db.save('Обновлены прочитанные сообщения', key, false);
}

async function markThreadRead(chat) {
  if (!chat.unread || !canWriteComms.value || trainingActive.value || document.hidden ||
    markingRead.has(chat.key) || markingAll) return;
  markingRead.add(chat.key);
  const messages = chat.messages || [];
  const messageIds = new Set(messages.filter(({ dir, read }) => dir === 'in' && !read).map(({ id }) => id));
  if (chat.lastMessage?.dir === 'in' && !chat.lastMessage.read) messageIds.add(chat.lastMessage.id);
  try {
    if (online.value && !chat.localOnly) {
      const through = Math.max(0, ...messages.map(({ seq }) => Number(seq) || 0));
      await commsApi.markChatRead(chat.key, through);
    }
    stopRefresh(chat.key);
    updateRead(chat.key, messageIds, chat.unread);
  } catch (error) {
    if (activeKey.value === chat.key) chatError.value = explainRequest(error, 'Не удалось отметить сообщения прочитанными.');
  } finally {
    markingRead.delete(chat.key);
  }
}

async function readAllChats() {
  if (!totalUnread.value || !canWriteComms.value || markingAll || trainingActive.value) return;
  markingAll = true;
  const snapshot = chatList.value.filter(({ unread }) => unread).map((conversation) => ({
    key: conversation.key,
    unread: conversation.unread,
    ids: new Set([...(conversation.messages || []), conversation.lastMessage]
      .filter((entry) => entry?.dir === 'in' && !entry.read).map(({ id }) => id)),
  }));
  try {
    if (online.value) await commsApi.readAll();
    stopRefresh();
    for (const { key, unread, ids } of snapshot) updateRead(key, ids, unread);
  } catch (error) {
    loadError.value = explainRequest(error, 'Не удалось отметить входящие прочитанными.');
  } finally { markingAll = false; }
}

function scrollBottom() {
  const key = activeKey.value;
  nextTick(() => {
    if (msgBox.value && activeKey.value === key) msgBox.value.scrollTop = msgBox.value.scrollHeight;
  });
}
watch(msgKindFilter, scrollBottom);

function isReplyTarget(message) {
  if (!message || message.kind === 'call' || message.source === 'manual') return false;
  if (message.dir === 'out' && !['chat', 'reply'].includes(message.source)) return false;
  if (message.kind === 'telegram') return !!(message.payload?.chatId || message.payload?.userIndex);
  if (message.kind === 'whatsapp') return !!message.phone;
  return !!(message.handle || message.phone || message.payload);
}
function whatsappAddress(chat) {
  if (!chat) return null;
  if (chat.whatsappPhone) return { phone: chat.whatsappPhone, contact: chat.contact };
  return chat.messages?.findLast((message) => message.kind === 'whatsapp' && message.phone)
    || (chat.kind === 'whatsapp' && chat.phone ? chat : null);
}
function whatsappTextAllowed(chat) {
  if (!chat) return false;
  if (Object.hasOwn(chat, 'whatsappTextUntil')) return Date.parse(chat.whatsappTextUntil) > Date.now();
  const message = chat.messages?.findLast((entry) => entry.kind === 'whatsapp' && entry.dir === 'in' && isReplyTarget(entry));
  return !!message && Date.parse(message.ts) + 24 * 60 * 60 * 1000 > Date.now();
}
const replyKinds = computed(() => {
  const chat = activeChat.value;
  return chat?.replyKinds || [...new Set((chat?.messages || []).filter(isReplyTarget).map(({ kind }) => kind))];
});
const sendKinds = computed(() => replyKinds.value.filter((kind) => channelAvailability(kind).canSend &&
  (kind !== 'whatsapp' || whatsappTextAllowed(activeChat.value))));
const sendKind = ref('');
watch(sendKinds, (available) => {
  if (available.includes(sendKind.value)) return;
  const lastInbound = activeChat.value?.messages?.findLast((message) =>
    message.dir === 'in' && available.includes(message.kind) && isReplyTarget(message));
  sendKind.value = lastInbound?.kind || available.at(-1) || '';
}, { immediate: true });
const canReply = computed(() => online.value && !loadingThread.value && canWriteComms.value && sendKinds.value.includes(sendKind.value));
const composeHint = computed(() => {
  if (loadingThread.value) return 'Загружаем историю диалога…';
  if (!online.value) return 'Нет связи с сервером. Отправка возобновится после подключения.';
  if (!canWriteComms.value) return 'Ваша роль позволяет просматривать переписку.';
  if (canReply.value) return channelAvailability(sendKind.value).state === 'queue' ?
    channelAvailability(sendKind.value).description : 'Enter — отправить · Shift + Enter — новая строка';
  if (replyKinds.value.includes('whatsapp') && channelAvailability('whatsapp').canSend && !whatsappTextAllowed(activeChat.value)) {
    return canUseWhatsAppTemplates.value ? 'После 24 часов без входящего сообщения используйте шаблон WhatsApp.'
      : 'Прошло 24 часа с последнего сообщения клиента. Для ответа нужен одобренный шаблон WhatsApp.';
  }
  if (replyKinds.value.length) return channelAvailability(replyKinds.value[0]).description;
  return chatKinds(activeChat.value || {}).includes('telegram')
    ? 'Для ответа в Telegram клиенту нужно написать подключённому боту.'
    : 'В этом диалоге нет подтверждённого адреса для отправки. Запись можно добавить в журнал.';
});

function addOutgoing(item) {
  if (!item?.id) return;
  stopRefresh(item.peerKey);
  db.mergeServerComms([item]);
  const chat = chatList.value.find(({ key }) => key === item.peerKey);
  if (!chat) return;
  if (!chat.messages.some(({ id }) => id === item.id)) chat.messages.push(item);
  chat.lastMessage = item;
  chat.lastTs = item.ts;
  chat.lastOutStatus = item.status;
}
function sendFeedback(result) {
  if (result.error) chatError.value = result.error;
  else chatNotice.value = result.sent ? 'Сообщение принято каналом.' : 'Сообщение поставлено в очередь.';
}
const unclearSend = 'Не удалось получить подтверждение отправки. Проверьте историю диалога перед повтором.';

async function sendChat() {
  const key = activeKey.value;
  const kind = sendKind.value;
  const draft = chatInput.value;
  const text = draft.trim();
  if (!canReply.value || !key || !text || chatSending.value || trainingActive.value) return;
  if (kind === 'whatsapp' && !whatsappTextAllowed(activeChat.value)) {
    chatError.value = 'Окно ответов WhatsApp закрыто. Для продолжения нужен одобренный шаблон.';
    return;
  }
  chatSending.value = true;
  chatError.value = '';
  chatNotice.value = '';
  try {
    setDraft(key, draft);
    const result = await commsApi.sendToChat(key, text, kind);
    addOutgoing(result.item);
    if (!result.error && getDraft(key) === draft) {
      setDraft(key, '');
      if (activeKey.value === key) chatInput.value = '';
    }
    if (activeKey.value === key) {
      sendFeedback(result);
      scrollBottom();
    }
    void loadChats(true);
  } catch (error) {
    if (activeKey.value === key) chatError.value = explainRequest(error, unclearSend);
    void loadChats(true);
  } finally {
    chatSending.value = false;
  }
}
function onInput() {
  if (activeKey.value) setDraft(activeKey.value, chatInput.value);
}
function onComposerKeydown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  void sendChat();
}

async function startNewChat() {
  if (!newChatAvailability.value.canSend || chatSending.value || trainingActive.value) return;
  const form = newChat.value;
  const byPhone = !HANDLE_KINDS.includes(form.kind);
  const target = recipientValue(form.kind, byPhone ? form.phone : form.handle);
  const message = form.text.trim();
  newChatError.value = '';
  if (!target || !message) {
    newChatError.value = 'Укажите получателя и текст сообщения.';
    return;
  }
  const problem = invalidRecipient(form.kind, target);
  if (problem) {
    newChatError.value = problem;
    return;
  }
  chatSending.value = true;
  try {
    const result = await commsApi.startChat({
      kind: form.kind, contact: form.contact.trim() || null,
      phone: byPhone ? target : null, handle: byPhone ? null : target, text: message,
    });
    addOutgoing(result.item);
    if (result.error) newChatError.value = result.error;
    else {
      newChatOpen.value = false;
      form.text = '';
    }
    if (result.item?.peerKey) await loadChats(true, result.item.peerKey);
    if (!result.error) sendFeedback(result);
  } catch (error) {
    newChatError.value = explainRequest(error, unclearSend);
  } finally { chatSending.value = false; }
}

function recipientValue(kind, value) {
  const target = value.trim();
  return kind === 'telegram' ? target.replace(/^https?:\/\/(?:www\.)?t\.me\//i, '').replace(/\/$/, '') : target;
}

function invalidRecipient(kind, address) {
  if (!address) return '';
  if (kind === 'email' && !/^[^\s@/\\]+@[^\s@/\\]+\.[^\s@/\\]+$/.test(address)) {
    return 'Введите адрес электронной почты, например name@example.com.';
  }
  if (recipientMeta(kind).field === 'handle' && /[/\\]/.test(address)) return 'Укажите логин или ID получателя без ссылки.';
  return '';
}

function showWhatsAppTemplate(chat) {
  const address = whatsappAddress(chat);
  if (!address || !canUseWhatsAppTemplates.value) return;
  newChat.value = { kind: 'whatsapp', phone: address.phone, contact: address.contact || '', handle: '', text: '' };
  newChatError.value = '';
  newChatOpen.value = true;
}
async function templateResult(result) {
  addOutgoing(result.item);
  if (result.item?.peerKey) await loadChats(true, result.item.peerKey);
  if (!result.error && (result.sent || result.item)) {
    newChatOpen.value = false;
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

function applyInboxWork(key, work) {
  const chat = chatList.value.find((row) => row.key === key);
  if (chat) {
    stopRefresh(key);
    chat.work = work;
  }
}

async function applySavedClient(key, { client, work }) {
  const chat = chatList.value.find((row) => row.key === key);
  if (chat) {
    stopRefresh(key);
    chat.farmId = client.id;
    chat.work = work;
    for (const message of chat.messages || []) message.farmId = client.id;
  }
  await Promise.allSettled([db.pullCrmState(), loadChats(true)]);
}

const showForm = ref(false);
const form = ref({ kind: 'call', dir: 'in', farmId: '', contact: '', phone: '', handle: '', text: '', note: '', status: 'Разговор', durationMin: 3 });
const formBusy = ref(false);
const formError = ref('');

async function saveComm() {
  if (formBusy.value || !canWriteComms.value || trainingActive.value) return;
  const entry = form.value;
  const address = recipientMeta(entry.kind).field;
  const recipient = recipientValue(entry.kind, entry[address]);
  formError.value = '';
  if (entry.kind !== 'call' && !entry.text.trim()) {
    formError.value = 'Введите текст для журнала.';
    return;
  }
  if (!entry.farmId && !recipient && !entry.contact.trim()) {
    formError.value = 'Укажите клиента, контакт или номер.';
    return;
  }
  const problem = invalidRecipient(entry.kind, recipient);
  if (problem) { formError.value = problem; return; }
  formBusy.value = true;
  try {
    await db.addComm({
      kind: entry.kind, dir: entry.dir, farmId: entry.farmId || null, contact: entry.contact.trim() || null,
      phone: address === 'phone' ? (recipient || null) : null,
      handle: address === 'handle' ? (recipient || null) : null,
      ...(entry.kind === 'call'
        ? { status: entry.status, duration: Math.max(0, Number(entry.durationMin) || 0) * 60, note: entry.note.trim() }
        : { text: entry.text.trim() }),
      read: true,
    });
    showForm.value = false;
    entry.text = '';
    entry.note = '';
    await loadChats();
  } catch (error) {
    formError.value = explainRequest(error, 'Не удалось сохранить запись в журнале. Повторите попытку.');
  } finally { formBusy.value = false; }
}

const autoRefresh = ref(true);
let pollTimer;
let polling = false;
async function tick() {
  if (!mounted || !autoRefresh.value || document.hidden || polling || loadingChats.value || loadingThread.value || chatSending.value) return;
  polling = true;
  try {
    const wasOnline = online.value;
    online.value = await checkApi();
    if (!mounted) return;
    if (online.value && (!wasOnline || Date.now() - lastSettingsCheck > 30000)) void loadSettings();
    if (online.value || wasOnline) await loadChats(true);
  } finally { polling = false; }
}
onMounted(async () => {
  window.addEventListener('focus', tick);
  document.addEventListener('visibilitychange', tick);
  await refreshChats();
  if (mounted) pollTimer = setInterval(tick, 4000);
});
onBeforeUnmount(() => {
  mounted = false;
  stopRefresh();
  clearInterval(pollTimer);
  window.removeEventListener('focus', tick);
  document.removeEventListener('visibilitychange', tick);
});
</script>

<template>
  <section class="comms-page" :class="{ 'conversation-open': activeChat }">
    <header class="pagehead comms-head">
      <div>
        <div class="comms-title">
          <h1>Коммуникации</h1>
          <ManualLink />
        </div>
        <p class="subtitle">Переписка, звонки и карточки клиентов</p>
      </div>
      <div class="actionbar comms-actions">
        <span class="connection-status" :class="{ connected: online }">
          {{ online ? 'Сервер на связи' : loadingChats ? 'Подключение…' : 'Локальная копия' }}
        </span>
        <button v-if="canWriteComms" type="button" class="btn slim" @click="showForm = !showForm" :aria-expanded="showForm">
          ＋ Запись в журнал
        </button>
      </div>
    </header>

    <div v-if="!online && !loadingChats" class="workspace-alert" role="status">
      <span>Сервер недоступен. Можно посмотреть сохранённую переписку.</span>
      <button type="button" class="btn slim ghost" @click="refreshChats">Подключиться снова</button>
    </div>
    <p v-if="db.commsSyncError && online" class="workspace-alert comms-error" role="status">
      {{ db.commsSyncError }}
    </p>
    <p v-if="chatError && !activeChat" class="workspace-alert comms-error" role="alert">{{ chatError }}</p>

    <section v-if="showForm" class="panel entry-panel" aria-labelledby="comms-journal-heading">
      <div class="entry-head">
        <h2 id="comms-journal-heading">Запись в журнале</h2>
        <button type="button" class="btn slim ghost" @click="showForm = false">Закрыть</button>
      </div>
      <form @submit.prevent="saveComm">
        <div class="formgrid">
          <label class="field">Канал
            <select v-model="form.kind" class="select">
              <option value="call">Звонок</option>
              <option value="telegram">Telegram</option>
              <option value="whatsapp">WhatsApp</option>
              <option v-for="ch in dynChannels" :key="ch.id" :value="ch.id">{{ ch.label }}</option>
            </select>
          </label>
          <label class="field">Направление
            <select v-model="form.dir" class="select">
              <option value="in">Входящее</option>
              <option value="out">Исходящее</option>
            </select>
          </label>
          <label class="field">Клиент
            <select v-model="form.farmId" class="select">
              <option value="">Без привязки к карточке</option>
              <option v-for="f in visibleFarms" :key="f.id" :value="f.id">{{ f.name }}</option>
            </select>
          </label>
          <label class="field">Контактное лицо
            <input v-model="form.contact" class="input" placeholder="Имя / должность" />
          </label>
          <label class="field">{{ recipientMeta(form.kind).label }}
            <input v-model="form[recipientMeta(form.kind).field]" :type="recipientMeta(form.kind).type"
                   class="input" :placeholder="recipientMeta(form.kind).placeholder" />
          </label>
          <template v-if="form.kind === 'call'">
            <label class="field">Итог звонка
              <select v-model="form.status" class="select">
                <option>Разговор</option>
                <option>Пропущенный</option>
                <option>Не дозвонились</option>
                <option>Перезвонить позже</option>
              </select>
            </label>
            <label class="field">Длительность, мин
              <input v-model.number="form.durationMin" type="number" min="0" class="input" />
            </label>
            <label class="field full">Резюме разговора
              <textarea v-model="form.note" class="textarea" placeholder="О чём договорились и какой следующий шаг?"></textarea>
            </label>
          </template>
          <label v-else class="field full">Сообщение
            <textarea v-model="form.text" class="textarea" placeholder="Текст для журнала…" maxlength="4000"></textarea>
          </label>
        </div>
        <p v-if="formError" class="comms-error" role="alert">{{ formError }}</p>
        <div class="entry-actions">
          <button type="button" class="btn ghost" @click="showForm = false">Отмена</button>
          <button type="submit" class="btn primary" :disabled="formBusy">Записать в журнал</button>
        </div>
      </form>
    </section>

    <section v-if="online && newChatOpen" id="new-comms-dialog" class="panel entry-panel" aria-labelledby="comms-new-heading">
      <header class="entry-head">
        <div class="entry-name">
          <ChannelIcon :kind="newChat.kind" :fallback="channelMeta[newChat.kind]?.icon" :size="24" />
          <h2 id="comms-new-heading">{{ newChat.kind === 'whatsapp' ? 'Новый диалог в WhatsApp' : 'Новый диалог' }}</h2>
        </div>
        <button type="button" class="btn slim ghost" :disabled="chatSending" @click="closeNewChat">Закрыть</button>
      </header>
      <div class="formgrid">
        <label class="field">Канал отправки
          <select v-model="newChat.kind" class="select" @change="onNewChatKindChange">
            <option v-for="kind in newChatKinds" :key="kind" :value="kind">{{ channelMeta[kind]?.label || kind }}</option>
          </select>
        </label>
        <label class="field">{{ recipientMeta(newChat.kind).label }}
          <input v-model="newChat[recipientMeta(newChat.kind).field]" :type="recipientMeta(newChat.kind).type"
                 class="input" :placeholder="recipientMeta(newChat.kind).placeholder" />
        </label>
        <label class="field">Имя получателя
          <input v-model="newChat.contact" class="input" placeholder="Необязательно" />
        </label>
        <p v-if="newChatAvailability.description" class="field full newchat-hint">
          {{ newChatAvailability.description }}
        </p>
      </div>
      <template v-if="newChat.kind === 'whatsapp'">
        <WhatsAppTemplateSender v-if="canUseWhatsAppTemplates" :phone="newChat.phone" :contact="newChat.contact" @result="templateResult" />
      </template>
      <form v-else class="newchat-message" @submit.prevent="startNewChat">
        <label class="field">Первое сообщение
          <textarea v-model="newChat.text" class="textarea" rows="2" maxlength="4000" placeholder="Текст сообщения…"></textarea>
        </label>
        <p v-if="newChatError" class="comms-error" role="alert">{{ newChatError }}</p>
        <div class="entry-actions">
          <button type="submit" class="btn primary" :disabled="chatSending || !newChatAvailability.canSend">
            {{ chatSending ? 'Отправляем…' : 'Начать диалог' }}
          </button>
        </div>
      </form>
    </section>

    <div class="messenger" :class="{ 'has-chat': activeChat }">
      <aside class="chat-side" aria-labelledby="inbox-heading">
        <div class="chat-side-head" data-tour="inbox-queue">
          <div class="inbox-title">
            <h2 id="inbox-heading" ref="inboxHeading" tabindex="-1">Диалоги</h2>
            <span v-if="totalUnread" class="badge" :aria-label="`Непрочитано: ${totalUnread}`">{{ totalUnread }}</span>
          </div>
          <button v-if="online && canWriteComms" type="button" class="btn slim primary" @click="toggleNewChat"
                  :aria-expanded="newChatOpen" aria-controls="new-comms-dialog">＋ Новый диалог</button>
        </div>
        <div class="inbox-controls">
          <input v-model="inboxQuery" type="search" class="input inbox-search" aria-label="Поиск диалогов" placeholder="Имя, телефон или сообщение" />
          <div class="inbox-select">
            <select v-model="inboxFilter" aria-label="Очередь диалогов" class="select">
              <option value="active">Активные</option>
              <option value="mine">Мои диалоги</option>
              <option value="overdue">Просроченные</option>
              <option value="closed">Закрытые</option>
              <option value="all">Все диалоги</option>
            </select>
            <button type="button" class="btn slim inbox-refresh" :disabled="loadingChats"
                    aria-label="Обновить диалоги" title="Обновить диалоги" @click="refreshChats">↻</button>
          </div>
          <div class="channel-select" role="group" aria-label="Фильтр по каналу">
            <button type="button" class="channel-chip" :aria-pressed="chatKindFilter === 'all'" @click="setChatKind('all')">Все</button>
            <button v-for="[kind, label] in BASE_FILTERS.filter(([key]) => key !== 'all')" :key="kind"
                    type="button" class="channel-chip" :class="{ 'channel-call': kind === 'call' }"
                    :aria-label="label" :title="label" :aria-pressed="chatKindFilter === kind" @click="setChatKind(kind)">
              <ChannelIcon :kind="kind" :size="15" />
              <span class="channel-label">{{ label }}</span>
            </button>
            <button v-for="ch in dynChannels" :key="ch.id" type="button" class="channel-chip"
                    :aria-pressed="chatKindFilter === ch.id" @click="setChatKind(ch.id)">
              <ChannelIcon :kind="ch.id" :fallback="ch.icon" :size="15" />
              <span>{{ ch.label }}</span>
            </button>
          </div>
          <div v-if="online && chatKindFilter !== 'all'" class="channel-info">
            <span class="channel-state" :class="{ connected: channelAvailability(chatKindFilter).canSend }">
              {{ channelAvailability(chatKindFilter).label }}
            </span>
          </div>
        </div>
        <div class="chat-list" :aria-busy="loadingChats && !sortedChats.length">
          <div v-if="loadError" class="inbox-feedback" role="status">
            <p class="comms-error">{{ loadError }}</p>
            <button type="button" class="btn slim" @click="refreshChats">Повторить</button>
          </div>
          <ul v-if="sortedChats.length" class="inbox-items" aria-label="Диалоги">
            <li v-for="chat in sortedChats" :key="chat.key">
              <button type="button" class="chat-item" :class="{ active: chat.key === activeKey, unread: chat.unread }"
                      :aria-current="chat.key === activeKey ? 'true' : undefined" @click="openChat(chat)">
                <span class="channel-tile">
                  <ChannelIcon :kind="chat.kind" :fallback="channelMeta[chat.kind]?.icon" :size="21" />
                </span>
                <span class="chat-item-main">
                  <span class="chat-item-top">
                    <span class="chat-name">{{ peerTitle(chat) }}</span>
                    <time v-if="chat.lastTs" class="chat-time" :datetime="chat.lastTs" :title="fmtDay(chat.lastTs)">
                      {{ fmtTime(chat.lastTs) }}
                    </time>
                  </span>
                  <span class="chat-item-bottom">
                    <span class="chat-preview">
                      <span v-if="chat.lastMessage?.dir === 'out'">Вы: </span>{{ chat.lastMessage?.text || chat.lastMessage?.note || chat.lastMessage?.status || 'Нет сообщений' }}
                    </span>
                    <span v-if="chat.unread" class="badge" :aria-label="`Непрочитано: ${chat.unread}`">{{ chat.unread }}</span>
                  </span>
                  <span v-if="chat.work && isResponseOverdue(chat.work)" class="chat-overdue">Просрочен ответ</span>
                  <span v-else-if="chat.work?.state && chat.work.state !== 'new'" class="chat-work-state">
                    {{ INBOX_STATES[chat.work.state] }}
                  </span>
                </span>
              </button>
            </li>
          </ul>
          <div v-else-if="!loadError" class="inbox-feedback" role="status">
            <p v-if="loadingChats">Загружаем диалоги…</p>
            <template v-else-if="inboxQuery || chatKindFilter !== 'all' || inboxFilter !== 'active'">
              <strong>Диалоги не найдены</strong>
              <p>Попробуйте другой запрос или фильтр.</p>
            </template>
            <template v-else>
              <strong>Пока нет диалогов</strong>
              <p>Здесь появятся входящие сообщения и сохранённые звонки.</p>
            </template>
          </div>
        </div>
        <div class="inbox-foot">
          <label class="refresh-control">
            <input type="checkbox" v-model="autoRefresh" />
            Автообновление
          </label>
          <button v-if="canWriteComms" type="button" class="btn slim ghost mark-read" :disabled="!totalUnread" @click="readAllChats">
            Прочитано всё
          </button>
        </div>
      </aside>

      <section class="chat-window" :aria-label="activeChat ? `Переписка: ${peerTitle(activeChat)}` : 'Переписка'">
        <template v-if="activeChat">
          <header class="chat-head">
            <button type="button" class="btn slim ghost mobile-thread-back" aria-label="К списку диалогов" @click="closeChat">←</button>
            <span class="channel-tile conversation-icon">
              <ChannelIcon :kind="activeChat.kind" :fallback="channelMeta[activeChat.kind]?.icon" :size="23" />
            </span>
            <div class="chat-identity">
              <h2 class="chat-head-name">{{ peerTitle(activeChat) }}</h2>
              <div class="chat-channel-label">
                {{ channelMeta[activeChat.kind]?.label || activeChat.kind }}
                <span v-if="peerSub(activeChat) && peerSub(activeChat) !== peerTitle(activeChat)"> · {{ peerSub(activeChat) }}</span>
              </div>
            </div>
            <div class="thread-actions">
              <select v-if="chatKinds(activeChat).length > 1" v-model="msgKindFilter" class="select kind-select" aria-label="Показать сообщения канала">
                <option value="all">Все каналы</option>
                <option v-for="kind in chatKinds(activeChat)" :key="kind" :value="kind">{{ channelMeta[kind]?.label || kind }}</option>
              </select>
              <button v-if="canUseWhatsAppTemplates && whatsappAddress(activeChat)"
                      type="button" class="btn slim" aria-label="Шаблон WhatsApp" @click="showWhatsAppTemplate(activeChat)">
                <ChannelIcon kind="whatsapp" :size="15" />
                <span>Шаблон</span>
              </button>
            </div>
          </header>

          <CommsInboxWork v-if="online && activeChat.work" :key="activeChat.key" :chat="activeChat"
                          :staff="inboxStaff" @updated="applyInboxWork" @client-saved="applySavedClient" />
          <div v-if="threadError" class="thread-feedback" role="alert">
            <span class="comms-error">{{ threadError }}</span>
            <button type="button" class="btn slim" @click="refreshChats">Повторить</button>
          </div>
          <div ref="msgBox" class="chat-messages" role="log" aria-label="История сообщений" aria-live="polite" aria-relevant="additions"
               :aria-busy="loadingThread" tabindex="0">
            <template v-for="(m, index) in chatMessages" :key="m.seq ?? m.id">
              <div v-if="dayGap(chatMessages, index)" class="day-divider"><span>{{ fmtDay(m.ts) }}</span></div>
              <div class="msg-row" :class="m.dir === 'out' ? 'mine' : 'theirs'">
                <article class="bubble" :class="{ failed: m.status === 'Ошибка доставки' }"
                         :aria-label="m.dir === 'out' ? 'Исходящее' : 'Входящее'">
                  <div v-if="m.kind === 'call'" class="call-title">
                    <ChannelIcon kind="call" :size="16" />
                    <strong>{{ m.status || 'Звонок' }}</strong>
                    <span v-if="m.duration">{{ Math.max(1, Math.round(m.duration / 60)) }} мин</span>
                  </div>
                  <div v-if="m.kind === 'call' && m.note" class="bubble-text">{{ m.note }}</div>
                  <div v-else-if="m.kind !== 'call'" class="bubble-text">{{ m.text || m.note || m.status || 'Сообщение' }}</div>
                  <div v-if="m.payload?.sendError && m.status === 'Ошибка доставки'" class="message-error">{{ m.payload.sendError }}</div>
                  <div class="bubble-meta">
                    <span v-if="m.source === 'manual' && m.kind !== 'call'">Журнал</span>
                    <span v-if="m.dir === 'out' && deliveryLabel(m.status)" :class="{ 'message-error': m.status === 'Ошибка доставки' }">
                      {{ deliveryLabel(m.status) }}
                    </span>
                    <time v-if="m.ts" :datetime="m.ts">{{ fmtTime(m.ts) }}</time>
                    <ChannelIcon v-if="m.kind !== 'call'" :kind="m.kind" :fallback="channelMeta[m.kind]?.icon" :size="12" />
                  </div>
                </article>
              </div>
            </template>
            <p v-if="!chatMessages.length && !threadError" class="thread-empty">
              {{ loadingThread ? 'Загружаем историю…' : msgKindFilter === 'all' ? 'В этом диалоге ещё нет сообщений.' : 'В выбранном канале нет сообщений.' }}
            </p>
          </div>

          <div class="chat-input">
            <p v-if="chatError" class="composer-feedback comms-error" role="alert">{{ chatError }}</p>
            <p v-if="chatNotice" class="composer-feedback comms-ok" role="status">{{ chatNotice }}</p>
            <form v-if="canReply" class="chat-composer" @submit.prevent="sendChat">
              <div class="composer-channel">
                <ChannelIcon :kind="sendKind" :fallback="channelMeta[sendKind]?.icon" :size="17" />
                <select v-model="sendKind" class="select send-kind" aria-label="Канал отправки">
                  <option v-for="kind in sendKinds" :key="kind" :value="kind">{{ channelMeta[kind]?.label || kind }}</option>
                </select>
              </div>
              <div class="chat-input-row">
                <textarea v-model="chatInput" class="textarea chat-textarea" rows="2" maxlength="4000"
                          aria-label="Сообщение" placeholder="Напишите сообщение…"
                          @input="onInput" @keydown="onComposerKeydown"></textarea>
                <button type="submit" class="btn primary send-btn" :disabled="!sendKind || !chatInput.trim() || chatSending" aria-label="Отправить сообщение">
                  <span class="send-label">{{ chatSending ? 'Отправляем…' : 'Отправить' }}</span>
                  <span class="send-arrow" aria-hidden="true">{{ chatSending ? '…' : '↑' }}</span>
                </button>
              </div>
              <p class="keyboard-hint">Enter — отправить, Shift + Enter — новая строка</p>
            </form>
            <p v-else class="compose-disabled">{{ composeHint }}</p>
          </div>
        </template>

        <div v-else class="chat-empty">
          <span class="empty-channel"><ChannelIcon kind="chat" :size="31" /></span>
          <h2>Откройте диалог</h2>
          <p>Выберите собеседника в списке, чтобы прочитать историю и ответить.</p>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.comms-title, .comms-actions, .entry-head, .entry-name, .entry-actions, .inbox-title, .inbox-select, .thread-actions,
.composer-channel, .chat-input-row, .call-title { display: flex; align-items: center; gap: 8px; }
.comms-title h1, .comms-head .subtitle { margin: 0; }
.comms-head { align-items: center; margin-block-end: 16px; }
.comms-title { margin-block-end: 4px; }
.comms-actions { align-self: center; }
.connection-status, .channel-state {
  display: inline-flex; align-items: center; gap: 7px; padding: 4px 8px;
  border-radius: 20px; background: var(--surface-soft); color: var(--muted); font-size: 11px; font-weight: 700; white-space: nowrap;
}
.connection-status::before, .channel-state::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.connection-status.connected, .channel-state.connected { color: var(--accent-ink); background: var(--accent-soft); }
.workspace-alert {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-block: 0 12px;
  padding: 9px 12px; border: 1px solid var(--warning-border); border-radius: 10px; background: var(--warning-soft);
  color: var(--warning-ink); font-size: 12px;
}
.entry-panel { margin-block-end: 14px; }
.entry-head { justify-content: space-between; margin-block-end: 12px; }
.entry-head h2 { margin: 0; }
.entry-actions { justify-content: flex-end; margin-block-start: 12px; }
.newchat-hint { margin: 0; color: var(--muted); font-size: 12px; }
.newchat-message { margin-block-start: 12px; }
.messenger {
  display: grid; grid-template-columns: minmax(260px, 1fr) minmax(0, 2.25fr);
  height: clamp(35rem, calc(100dvh - 11rem), 52rem);
  border: 1px solid var(--border); border-radius: 18px; overflow: hidden; background: var(--panel); box-shadow: var(--shadow-soft);
}
.chat-side, .chat-window { min-height: 0; min-width: 0; display: flex; flex-direction: column; }
.chat-side { border-inline-end: 1px solid var(--border); background: var(--panel); }
.chat-side-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 15px 14px 9px; }
.inbox-title h2 { font-size: 17px; }
.inbox-controls { display: grid; gap: 8px; padding: 0 14px 10px; border-block-end: 1px solid var(--border); container-type: inline-size; }
.inbox-search, .inbox-select select { padding-block: 7px; }
.inbox-refresh { min-width: 36px; font-size: 17px; line-height: 1.05; }
.channel-select { display: flex; align-items: center; gap: 5px; padding-block: 2px 5px; overflow-x: auto; overscroll-behavior-inline: contain; }
.channel-chip {
  display: inline-flex; flex: none; align-items: center; gap: 5px; min-height: 30px; padding: 3px 8px; border-radius: 20px;
  border: 1px solid var(--control-border); background: var(--panel); color: var(--muted); font-size: 11px; font-weight: 700;
}
.channel-chip:hover { border-color: var(--accent-border); color: var(--ink); }
.channel-chip[aria-pressed="true"] { border-color: var(--accent-border); color: var(--accent-ink); background: var(--accent-soft); }
.channel-info { line-height: 1.15; }
.chat-list { flex: 1; min-height: 0; overflow-y: auto; padding: 5px 6px; overscroll-behavior-y: contain; }
.inbox-items { list-style: none; padding: 0; margin: 0; }
.chat-item {
  width: 100%; display: flex; align-items: center; gap: 9px; padding: 10px 8px; border: 1px solid transparent; border-radius: 10px;
  color: var(--ink); background: transparent; text-align: start; min-width: 0;
}
.chat-item:hover { background: var(--surface-hover); }
.chat-item.active { background: var(--accent-soft); border-color: var(--accent-border); }
.channel-tile { display: grid; place-items: center; flex: none; width: 38px; height: 38px; border: 1px solid var(--border); border-radius: 12px; background: var(--panel); }
.chat-item-main { display: flex; flex-direction: column; flex: 1; gap: 2px; min-width: 0; }
.chat-item-top, .chat-item-bottom { display: flex; justify-content: space-between; gap: 6px; min-width: 0; align-items: baseline; }
.chat-name, .chat-preview { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.chat-name { font-size: 13px; font-weight: 680; }
.chat-item.unread .chat-name { font-weight: 800; }
.chat-preview, .chat-time, .chat-work-state, .chat-overdue { color: var(--muted); font-size: 11.5px; }
.chat-time { flex: none; font-variant-numeric: tabular-nums; }
.chat-overdue { color: var(--danger-ink); font-weight: 700; }
.badge {
  display: inline-grid; place-items: center; flex: none; min-width: 20px; min-height: 20px; padding: 1px 5px;
  border-radius: 20px; background: var(--primary); color: var(--primary-ink); font-size: 11px; font-weight: 750;
}
.inbox-foot { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; padding: 8px 14px; border-block-start: 1px solid var(--border); }
.refresh-control { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--muted); cursor: pointer; }
.refresh-control input { accent-color: var(--primary); }
.mark-read { font-size: 11px; }
.inbox-feedback { padding: 20px 8px; text-align: center; color: var(--muted); font-size: 12px; }
.inbox-feedback strong { color: var(--ink); }
.inbox-feedback p { margin-block: 4px 0; }
.inbox-feedback button { margin-block-start: 8px; }
.chat-window { background: var(--surface-soft); }
.chat-head {
  display: flex; align-items: center; flex-wrap: wrap; gap: 9px; padding: 12px 15px;
  background: var(--panel); border-block-end: 1px solid var(--border);
}
.conversation-icon { width: 42px; height: 42px; }
.chat-identity { flex: 1; min-width: 100px; }
.chat-head-name { overflow: hidden; font-size: 17px; white-space: nowrap; text-overflow: ellipsis; }
.chat-channel-label { color: var(--muted); font-size: 11.5px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.thread-actions { margin-inline-start: auto; flex-wrap: wrap; }
.thread-actions .btn { display: inline-flex; align-items: center; gap: 5px; }
.kind-select { width: auto; max-width: 150px; padding: 6px 8px; font-size: 12px; }
.mobile-thread-back { display: none; }
.chat-window :deep(.inbox-work) { max-height: 14rem; overflow: auto; padding: 7px 14px; border-color: var(--border); background: var(--panel); }
.chat-window :deep(.client-capture) { border-color: var(--border); background: var(--surface-soft); }
.chat-window :deep(.work-error) { color: var(--danger-ink); }
.chat-window :deep(.client-saved) { color: var(--accent-ink); }
.thread-feedback { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px; padding: 6px 14px; background: var(--panel); border-block-end: 1px solid var(--border); font-size: 12px; }
.chat-messages {
  flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; padding: 13px clamp(12px, 3vw, 28px) 18px;
  overscroll-behavior-y: contain; background-image: radial-gradient(var(--border) .7px, transparent .7px); background-size: 19px 19px;
}
.day-divider { text-align: center; margin-block: 4px; }
.day-divider span {
  display: inline-block; padding: 3px 10px; border: 1px solid var(--border); border-radius: 18px; color: var(--muted); background: var(--panel);
  font-size: 11px; font-weight: 700;
}
.msg-row { display: flex; }
.msg-row.mine { justify-content: flex-end; }
.bubble {
  min-width: 0; max-width: min(82%, 34rem); padding: 8px 10px 6px; border: 1px solid var(--border); border-radius: 14px;
  background: var(--panel); color: var(--ink); font-size: 13.5px; line-height: 1.45; overflow-wrap: anywhere;
}
.msg-row.theirs .bubble { border-end-start-radius: 4px; }
.msg-row.mine .bubble { background: var(--accent-soft); border-color: var(--accent-border); border-end-end-radius: 4px; }
.msg-row .bubble.failed { background: var(--danger-soft); border-color: var(--danger-border); }
.bubble-text { white-space: pre-wrap; }
.bubble-meta { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 3px 6px; margin-block-start: 4px; color: var(--muted); font-size: 10.5px; }
.bubble-meta time { font-variant-numeric: tabular-nums; }
.call-title { gap: 5px; }
.call-title span, .message-error { font-size: 11px; }
.call-title span { color: var(--muted); }
.message-error, .comms-error { color: var(--danger-ink); }
.comms-ok { color: var(--accent-ink); }
.thread-empty { margin-block: 12px; text-align: center; color: var(--muted); font-size: 13px; }
.chat-input { padding: 9px 14px; background: var(--panel); border-block-start: 1px solid var(--border); }
.chat-composer { display: grid; gap: 6px; }
.composer-channel { gap: 6px; }
.send-kind { width: auto; max-width: calc(100% - 30px); padding: 3px 7px; font-size: 11px; }
.chat-input-row { align-items: end; }
.chat-textarea { flex: 1; min-height: 44px; max-height: 140px; resize: vertical; }
.send-btn { min-height: 44px; align-self: end; }
.send-arrow { display: none; }
.keyboard-hint, .compose-disabled, .composer-feedback { margin: 0; font-size: 11px; }
.keyboard-hint, .compose-disabled { color: var(--muted); }
.composer-feedback { margin-block-end: 5px; }
.chat-empty { display: grid; justify-items: center; align-content: center; gap: 8px; min-height: 240px; height: 100%; padding: 20px; text-align: center; }
.chat-empty h2, .chat-empty p { margin: 0; }
.chat-empty p { max-width: 240px; color: var(--muted); font-size: 13px; }
.empty-channel { display: grid; place-items: center; width: 56px; height: 56px; border-radius: 16px; background: var(--accent-soft); color: var(--accent-ink); }

@container (max-width: 320px) {
  .channel-chip { padding-inline: 6px; }
  .channel-call .channel-label { display: none; }
}

@media (max-width: 900px) {
  .messenger { display: block; height: auto; }
  .chat-side { min-height: 24rem; max-height: max(28rem, calc(100dvh - 11rem)); border-inline-end: 0; }
  .chat-window { display: none; }
  .has-chat .chat-side { display: none; }
  .has-chat .chat-window { display: flex; height: clamp(22rem, calc(100dvh - 14rem), 52rem); }
  .mobile-thread-back { display: inline-flex; justify-content: center; min-width: 32px; font-size: 16px; }
  .conversation-open .comms-head { display: none; }
  .chat-head { padding: 9px 10px; }
  .chat-window :deep(.inbox-work) { max-height: min(12rem, 33dvh); }
  .bubble { max-width: 89%; }
  .keyboard-hint { display: none; }
}

@media (min-width: 751px) and (max-width: 900px) {
  .has-chat .chat-window { height: clamp(22rem, calc(100dvh - 8rem), 52rem); }
}

@media (max-width: 475px) {
  .comms-head { display: flex; flex-wrap: wrap; gap: 8px; }
  .comms-head .comms-actions { margin-block-start: 0; }
  .chat-head { gap: 6px; }
  .conversation-icon { width: 36px; height: 36px; }
  .chat-head-name { font-size: 15px; }
  .chat-identity { min-width: 90px; }
  .thread-actions { gap: 0; }
  .thread-actions .kind-select { max-width: 110px; }
  .thread-actions .btn { padding-inline: 6px; }
  .chat-messages { padding-inline: 9px; }
  .chat-input { padding-inline: 9px; }
  .send-btn { width: 44px; padding: 5px; }
  .send-label { display: none; }
  .send-arrow { display: block; font-size: 21px; }
}
</style>
