import { defineStore } from 'pinia';
import { SAMPLE } from '@/data/sample';
import { commsApi, apiEnabled, checkApi } from '@/api/commsClient';
import { logisticsApi } from '@/api/logisticsClient';

// apiEnabled — функция (см. commsClient.js); вызываем как функцию
const apiOn = () => typeof apiEnabled === 'function' ? apiEnabled() : !!apiEnabled;

const KEY = 'biotorf-business-os-mvp-2026-10';

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return structuredClone(SAMPLE);
    const parsed = JSON.parse(raw);
    // миграция v1 → v2: убираем тестовые коммуникации из сохранённого демо-состояния
    if (!parsed.version || parsed.version < 2) {
      parsed.comms = [];
      parsed.version = 2;
    }
    // дополняем отсутствующие коллекции как в исходнике
    parsed.social ??= structuredClone(SAMPLE.social || []);
    parsed.contacts ??= [];
    parsed.clientNotes ??= [];
    parsed.clientDocs ??= [];
    parsed.media ??= [];
    parsed.marketingAttributions ??= [];
    parsed.preferences ??= {};
    parsed.journeys ??= [];
    parsed.quotes ??= [];
    parsed.comms ??= [];
    parsed.logistics ??= [];
    return parsed;
  } catch {
    return structuredClone(SAMPLE);
  }
}

export const useDbStore = defineStore('db', {
  state: () => ({ data: load(), commsSyncError: null }),
  getters: {
    farms: (s) => s.data.farms,
    deals: (s) => s.data.deals,
    pilots: (s) => s.data.pilots,
    orders: (s) => s.data.orders,
    tasks: (s) => s.data.tasks,
    knowledge: (s) => s.data.knowledge,
    social: (s) => s.data.social,
    skus: (s) => s.data.skus,
    leads: (s) => s.data.leads,
    warehouse: (s) => s.data.warehouse,
    comms: (s) => s.data.comms,
    logistics: (s) => s.data.logistics || [],
    // хелперы
    farmById: (s) => (id) => s.data.farms.find((x) => x.id === id),
    skuById: (s) => (id) => s.data.skus.find((x) => x.id === id) || { name: id, pack: 0 },
    lateTasks: (s) => s.data.tasks.filter((t) => t.status !== 'Выполнена' && isLate(t.due)),
  },
  actions: {
    // ── Коммуникации: звонки и сообщения внутри сервиса ──────────────
    // Если поднят бэкенд (backend/, порт 8787) — лента живёт в SQLite и
    // синхронизируется между сотрудниками; иначе — локально в localStorage.
    async addComm(entry) {
      this.data.comms ??= [];
      const item = {
        id: 'C-' + String(Date.now()).slice(-8),
        ts: new Date().toISOString(),
        read: true,
        ...entry,
      };
      this.data.comms.unshift(item);
      this.data.comms.sort((a, b) => (a.ts < b.ts ? 1 : -1));
      this.save('Коммуникация добавлена', entry.farmId || 'Неизвестный контакт');
      if (apiOn()) {
        try {
          const remote = await commsApi.create(entry);
          if (remote?.id) {
            const i = this.data.comms.findIndex((x) => x.id === item.id);
            if (i >= 0) this.data.comms[i] = { ...item, id: remote.id, source: remote.source };
            this.save();
          }
          this.commsSyncError = null;
        } catch (e) { this.commsSyncError = e.message; }
      }
      return item;
    },
    async markCommRead(id) {
      const c = this.data.comms.find((x) => x.id === id);
      if (c && !c.read) {
        c.read = true;
        c.updatedAt = new Date().toISOString();
        this.save('Прочитано сообщение', id);
        if (apiOn()) {
          try { await commsApi.markRead(id); this.commsSyncError = null; }
          catch (e) { this.commsSyncError = e.message; }
        }
      }
    },
    async markAllCommsRead() {
      this.data.comms.forEach((c) => (c.read = true));
      this.save('Отмечены прочитанными все сообщения', 'Коммуникации');
      if (apiOn()) {
        try { await commsApi.readAll(); this.commsSyncError = null; }
        catch (e) { this.commsSyncError = e.message; }
      }
    },
    async linkCommToFarm(commId, farmId) {
      const c = this.data.comms.find((x) => x.id === commId);
      if (c) {
        c.farmId = farmId;
        this.save('Коммуникация привязана к клиенту', `${commId} → ${farmId}`);
        if (apiOn()) {
          try { await commsApi.link(commId, farmId); this.commsSyncError = null; }
          catch (e) { this.commsSyncError = e.message; }
        }
      }
    },
    // Подтянуть ленту с бэкенда (вызывается при открытии «Коммуникаций»
    // и периодически для автообновления статусов доставки).
    // quiet=true — не показывать ошибку, если сервер временно недоступен.
    async syncComms(quiet = false) {
      if (!(await checkApi())) return false;   // бэкенд не запущен — остаёмся на localStorage
      try {
        const [{ items }, capsRes] = await Promise.all([
          commsApi.list({ limit: 500 }),
          commsApi.capabilities().catch(() => null),
        ]);
        this.mergeServerComms(items);
        this.commsSyncError = null;
        return true;
      } catch (e) {
        if (!quiet) this.commsSyncError = e.message;
        return false;
      }
    },
    // Осторожное слияние серверной ленты с локальной: берём свежие статусы
    // доставки/прочтения, но НЕ перетираем записи, которые пользователь только
    // что создал или изменил локально (иначе фоновое автообновление могло бы
    // вернуть «В очереди» вместо только что проставленного «Доставлено»).
    mergeServerComms(items) {
      const localById = new Map(this.data.comms.map((c) => [c.id, c]));
      const seen = new Set();
      const merged = items.map((r) => {
        seen.add(r.id);
        const l = localById.get(r.id);
        if (!l) return r;
        const lt = Date.parse(l.updatedAt || l.ts || '') || 0;
        const rt = Date.parse(r.updatedAt || r.ts || '') || 0;
        // локальная запись свежее серверной (например, ответ уже доставлен
        // и подтверждён в этой вкладке) — оставляем её поля, id берём серверный
        if (lt > rt) return { ...r, ...l, id: r.id };
        return r;
      });
      // локальные записи, которых ещё нет на сервере (не успели сохраниться)
      for (const c of this.data.comms) if (!seen.has(c.id)) merged.push(c);
      merged.sort((a, b) => (a.ts < b.ts ? 1 : -1));
      this.data.comms = merged;
      this.save();
    },
    // Реальный ответ клиенту из ленты: сервер отправляет в Telegram и
    // возвращает созданную исходящую запись — добавляем её в локальную ленту.
    async sendCommReply(commId, text) {
      if (!apiOn()) throw new Error('Бэкенд не подключён — отправка невозможна');
      const res = await commsApi.send(commId, text);
      if (res?.item) {
        // помечаем время изменения — слияние при автообновлении не перетрёт
        // статус «Доставлено», если подтверждение ещё не дошло с сервера
        res.item.updatedAt = new Date().toISOString();
        this.data.comms.unshift(res.item);
        this.data.comms.sort((a, b) => (a.ts < b.ts ? 1 : -1));
        this.save('Ответ отправлен', commId);
      }
      return res;
    },

    // ── Логистика: поставки и выгрузки (отгрузки) товара ──────────────
    // Как и с коммуникациями: если бэкенд доступен — документы общие (SQLite),
    // иначе живут локально в localStorage. Локальные несохранённые на сервер
    // документы догоняются синхронизацией при возможности.
    async syncLogistics() {
      this.data.logistics ??= [];
      const remote = await logisticsApi.list();
      if (!remote) return false;               // бэкенд недоступен — остаёмся локальными
      const localById = new Map(this.data.logistics.map((d) => [d.id, d]));
      const seen = new Set();
      const merged = remote.map((r) => {
        seen.add(r.id);
        const l = localById.get(r.id);
        if (!l) return r;
        const lt = Date.parse(l.updatedAt || l.date || '') || 0;
        const rt = Date.parse(r.updatedAt || r.date || '') || 0;
        return lt > rt ? { ...r, ...l, id: r.id } : r;
      });
      for (const d of this.data.logistics) {
        if (!seen.has(d.id)) {
          // локальный документ ещё не доехал до сервера — пробуем отправить
          try { const up = await logisticsApi.create(d); merged.push(up); }
          catch { merged.push(d); }
        }
      }
      merged.sort((a, b) => ((a.date || '') < (b.date || '') ? 1 : -1));
      this.data.logistics = merged;
      this.save();
      return true;
    },
    async addLogistics(payload) {
      this.data.logistics ??= [];
      const item = {
        id: 'LOC-' + String(Date.now()).slice(-9),
        act: null,
        ...payload,
        updatedAt: new Date().toISOString(),
      };
      this.data.logistics.unshift(item);
      this.save(payload.kind === 'dispatch' ? 'Создана выгрузка' : 'Создана поставка', payload.number || item.id);
      try {
        const remote = await logisticsApi.create(payload);
        if (remote?.id) {
          const i = this.data.logistics.findIndex((x) => x.id === item.id);
          if (i >= 0) this.data.logistics[i] = { ...item, ...remote };
          this.save();
        }
      } catch { /* офлайн — остаётся локально, догонит syncLogistics */ }
      return item;
    },
    async updateLogistics(id, payload) {
      const i = (this.data.logistics || []).findIndex((d) => d.id === id);
      if (i < 0) return null;
      const prev = this.data.logistics[i];
      const next = { ...prev, ...payload, id, updatedAt: new Date().toISOString() };
      this.data.logistics[i] = next;
      this.save('Документ логистики обновлён', payload.number || id);
      try { await logisticsApi.update(id, payload); }
      catch { /* сервер недоступен — изменения локальные */ }
      return next;
    },
    async removeLogistics(id) {
      this.data.logistics = (this.data.logistics || []).filter((d) => d.id !== id);
      this.save('Удалён документ логистики', id);
      try { await logisticsApi.remove(id); } catch { /* noop */ }
    },

    save(action = 'Изменены данные', object = 'Система') {
      this.data.audit ??= [];
      this.data.audit.unshift({ time: new Date().toISOString(), action, object });
      this.data.audit = this.data.audit.slice(0, 300);
      try {
        localStorage.setItem(KEY, JSON.stringify(this.data));
      } catch {
        console.warn('localStorage full');
      }
    },
    reset() {
      this.data = structuredClone(SAMPLE);
      localStorage.removeItem(KEY);
    },
    replaceAll(next) {
      this.data = next;
      this.save('Импорт', 'System');
    },
  },
});

export function isLate(d) {
  return !!(d && d < new Date().toISOString().slice(0, 10));
}