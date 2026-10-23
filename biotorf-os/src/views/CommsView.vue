<script setup>
import { ref, computed, onMounted } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { apiState, COMMS_API_URL, caps } from '@/api/commsClient';
import StatusPill from '@/components/ui/StatusPill.vue';

const db = useDbStore();
const ui = useUiStore();

const KIND_META = {
  call:     { label: 'Звонок',   icon: '☎' },
  telegram: { label: 'Telegram', icon: '✈' },
  whatsapp: { label: 'WhatsApp', icon: '◔' },
};

const FILTERS = [
  ['all', 'Все'],
  ['call', 'Звонки'],
  ['telegram', 'Telegram'],
  ['whatsapp', 'WhatsApp'],
  ['unread', 'Непрочитанные'],
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
      phone: f.kind === 'whatsapp' ? (f.phone || null) : null,
      handle: f.kind === 'telegram' ? (f.handle || null) : null,
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
      if (['call', 'telegram', 'whatsapp'].includes(f) && c.kind !== f) return false;
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

onMounted(async () => {
  // если поднят бэкенд коммуникаций (backend/, порт 8787) — лента общая, из SQLite
  await db.syncComms();
  if (ui.commsFocusFarm) {
    ui.search = db.farmById(ui.commsFocusFarm)?.name || '';
    ui.commsFocusFarm = null;
  }
});
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Коммуникации</h1>
        <div class="subtitle">Единая лента: звонки с телефона, Telegram и WhatsApp. Всё общение с клиентом — внутри сервиса.</div>
      </div>
      <div class="actionbar">
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
        <div v-if="form.kind !== 'telegram'" class="field">
          <label>Номер телефона</label>
          <input v-model="form.phone" class="input" placeholder="+996 …" />
        </div>
        <div v-if="form.kind === 'telegram'" class="field">
          <label>Ник в Telegram</label>
          <input v-model="form.handle" class="input" placeholder="@username" />
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
                {{ KIND_META[c.kind].icon }} {{ KIND_META[c.kind].label }}
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

    <!-- панель быстрого ответа -->
    <Teleport to="body">
      <div v-if="replyTarget" class="modal-backdrop" @click.self="replyTarget = null">
        <div class="modal" role="dialog" aria-label="Ответ клиенту">
          <div class="modal-title">
            <h2>Ответ · {{ KIND_META[replyTarget.kind].label }}</h2>
            <button class="btn ghost slim" @click="replyTarget = null">✕</button>
          </div>
          <div class="modal-body">
            <div class="mini" style="margin-bottom:4px">Сообщение клиента · {{ fmtTs(replyTarget.ts) }}</div>
            <div class="comms-bubble" style="margin-bottom:12px">{{ replyTarget.text }}</div>
            <textarea v-model="replyText" class="textarea" rows="4" placeholder="Ваш ответ… (Ctrl+Enter — отправить)" autofocus
                      @keydown.ctrl.enter.prevent="sendReply"></textarea>
            <div v-if="apiState.online && replyTarget.kind === 'telegram' && caps.telegramSend" class="mini comms-ok" style="margin-top:8px">
              ✉ Сообщение будет реально отправлено клиенту в Telegram от имени бота
            </div>
            <div v-else-if="apiState.online && replyTarget.kind === 'telegram'" class="mini comms-warn" style="margin-top:8px">
              ⚠ Отправка через бота не настроена на сервере (TELEGRAM_BOT_TOKEN пуст) —
              ответ сохранится только в ленте. Впишите токен в .env и перезапустите стек.
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
</style>
