import { defineStore } from 'pinia';
import { SAMPLE } from '@/data/sample';
import { commsApi, apiEnabled, checkApi } from '@/api/commsClient';

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
      if (apiEnabled) {
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
        this.save('Прочитано сообщение', id);
        if (apiEnabled) {
          try { await commsApi.markRead(id); this.commsSyncError = null; }
          catch (e) { this.commsSyncError = e.message; }
        }
      }
    },
    async markAllCommsRead() {
      this.data.comms.forEach((c) => (c.read = true));
      this.save('Отмечены прочитанными все сообщения', 'Коммуникации');
      if (apiEnabled) {
        try { await commsApi.readAll(); this.commsSyncError = null; }
        catch (e) { this.commsSyncError = e.message; }
      }
    },
    async linkCommToFarm(commId, farmId) {
      const c = this.data.comms.find((x) => x.id === commId);
      if (c) {
        c.farmId = farmId;
        this.save('Коммуникация привязана к клиенту', `${commId} → ${farmId}`);
        if (apiEnabled) {
          try { await commsApi.link(commId, farmId); this.commsSyncError = null; }
          catch (e) { this.commsSyncError = e.message; }
        }
      }
    },
    // Подтянуть ленту с бэкенда (вызывается при открытии «Коммуникаций»)
    async syncComms() {
      if (!(await checkApi())) return false;   // бэкенд не запущен — остаёмся на localStorage
      try {
        const { items } = await commsApi.list({ limit: 500 });
        this.data.comms = items;
        this.save();
        this.commsSyncError = null;
        return true;
      } catch (e) {
        this.commsSyncError = e.message;
        return false;
      }
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