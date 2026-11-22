import { defineStore } from 'pinia';
import { markRaw } from 'vue';
import { acceptCrmState, captureChanges, crmPayload, hasCrmChanges, loadCrmSync, persistPending, serializeCrm, snapshot } from '@/data/crmSync';
import { commsApi, apiEnabled, checkApi } from '@/api/commsClient';
import { logisticsApi } from '@/api/logisticsClient';
import { crmApi } from '@/api/crmClient';

// apiEnabled — функция (см. commsClient.js); вызываем как функцию
const apiOn = () => typeof apiEnabled === 'function' ? apiEnabled() : !!apiEnabled;

const KEY = 'biotorf-business-os-mvp-2026-10';

// Пустое состояние: без тестовых записей, только справочники и настройки
function emptyState() {
  return {
    version: 3,
    mode: 'production',
    users: [],
    farms: [], leads: [], deals: [], journeys: [], pilots: [], quotes: [],
    orders: [], invoices: [], shipments: [], tasks: [], contacts: [],
    clientNotes: [], applications: [], payments: [], media: [], social: [],
    knowledge: [], skus: [], warehouse: [], production: [], clientDocs: [],
    comms: [], logistics: [], marketingAttributions: [], preferences: {},
    // Справочники для выпадающих списков (значение + кнопка «＋» в модалке).
    // Значения собираются автоматически из записей, сюда добавляются вручную.
    lists: {
      regions: ['Краснодарский край', 'Ростовская область', 'Ставропольский край', 'Алтайский край'],
      crops: ['пшеница озимая', 'кукуруза', 'подсолнечник', 'соя', 'сахарная свёкла'],
      sources: ['выставка', 'сайт', 'телеграм', 'реферал', 'холодный звонок'],
      owners: [],
      statuses: ['активное'],
      types: ['агрохолдинг', 'КФХ', 'ИП'],
      unitPack: ['5 л', '10 л', '200 мл', '1 л'],
      locations: ['склад А', 'склад Б'],
      transport: [], drivers: [], plates: [], shifts: [], operators: [], platforms: [],
    },
    stages: ['Новый лид', 'Связаться', 'Контакт установлен', 'Квалификация',
      'Потенциальный клиент', 'Агрономическая диагностика', 'Предложен пилот',
      'Пилот согласован', 'Пилот идет', 'Результат получен', 'Экономика рассчитана',
      'КП отправлено', 'Переговоры', 'Счет/договор', 'Ожидается оплата', 'Оплачено',
      'Отгружено', 'Получено клиентом', 'Сопровождение', 'Повторный заказ',
      'Сезонный контракт'],
    pilotStages: ['Новый пилот', 'Квалификация', 'Ожидается согласование',
      'BIOTORF зарезервирован', 'BIOTORF отправлен', 'BIOTORF получен',
      'Ожидается первая обработка', 'Испытание идет', 'Ожидается промежуточный контроль',
      'Ожидается итоговый результат', 'Результат получен', 'Экономика рассчитана',
      'Пилот успешен', 'Пилот без подтвержденного эффекта', 'Пилот приостановлен',
      'Пилот прекращен', 'Передан в продажи', 'Завершен'],
  };
}

// Коллекции, которые синхронизируются с бэкендом (backend/crm.py)
const SYNC_COLLECTIONS = [
  'farms', 'leads', 'deals', 'journeys', 'pilots', 'quotes', 'orders',
  'invoices', 'shipments', 'tasks', 'contacts', 'clientNotes',
  'applications', 'payments', 'media', 'social', 'knowledge', 'skus',
  'warehouse', 'production', 'clientDocs',
];

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return emptyState();
    const parsed = JSON.parse(raw);
    // миграция v1 → v2: убираем тестовые коммуникации из сохранённого демо-состояния
    if (!parsed.version || parsed.version < 2) {
      parsed.comms = [];
      parsed.version = 2;
    }
    // дополняем отсутствующие коллекции пустыми значениями (без демо-данных)
    parsed.social ??= [];
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
    // миграция v3 → v4: справочники выпадающих списков (данные пользователя сохраняются)
    if (!parsed.lists || !parsed.lists.regions) {
      parsed.lists = emptyState().lists;
      parsed.version = 4;
    }
    // миграция v2 → v3: связанные с маршрутами поля и реестры документов
    if (!parsed.version || parsed.version < 3) {
      for (const d of parsed.deals || []) { d.journeyId ??= null; }
      for (const p of parsed.pilots || []) { p.dealId ??= null; p.journeyId ??= null; }
      for (const o of parsed.orders || []) { o.journeyId ??= null; o.quoteId ??= null; }
      for (const inv of parsed.invoices || []) { inv.journeyId ??= null; inv.paid = inv.paid ?? false; }
      parsed.shipments ??= [];
      parsed.version = 3;
    }
    return parsed;
  } catch {
    return emptyState();
  }
}

export const useDbStore = defineStore('db', {
  state: () => {
    const data = load();
    return {
      data,
      crmSync: markRaw(loadCrmSync(data, SYNC_COLLECTIONS)),
      commsSyncError: null,
      crmSyncError: null,
      serverOnline: false,
    };
  },
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
    journeys: (s) => s.data.journeys || [],
    quotes: (s) => s.data.quotes || [],
    invoices: (s) => s.data.invoices || [],
    shipments: (s) => s.data.shipments || [],
    // хелперы
    farmById: (s) => (id) => s.data.farms.find((x) => x.id === id),
    skuById: (s) => (id) => s.data.skus.find((x) => x.id === id) || { name: id, pack: 0 },
    lateTasks: (s) => s.data.tasks.filter((t) => t.status !== 'Выполнена' && isLate(t.due)),
    journeyById: (s) => (id) => (s.data.journeys || []).find((j) => j.id === id),
    leadById: (s) => (id) => s.data.leads.find((x) => x.id === id),
    dealById: (s) => (id) => s.data.deals.find((x) => x.id === id),
    pilotById: (s) => (id) => s.data.pilots.find((x) => x.id === id),
    quoteById: (s) => (id) => (s.data.quotes || []).find((x) => x.id === id),
    orderById: (s) => (id) => s.data.orders.find((x) => x.id === id),
    invoiceById: (s) => (id) => (s.data.invoices || []).find((x) => x.id === id),
    invoiceBalance: (s) => (invoice) => {
      const due = Number(invoice.amount) || 0;
      const paid = (s.data.payments || []).filter((payment) => payment.invoiceId === invoice.id)
        .reduce((sum, payment) => sum + (Number(payment.amount) || 0), 0);
      return invoice.paid || invoice.status === 'Оплачен' ? 0 : Math.max(0, Math.round((due - paid) * 100) / 100);
    },
  },
  actions: {
    // ── Коммуникации: звонки и сообщения внутри сервиса ──────────────
    // Если поднят бэкенд (backend/, порт 8787) — лента живёт в SQLite и
    // синхронизируется между сотрудниками; иначе — локально в localStorage.
    async addComm(entry) {
      const remote = apiOn() ? await commsApi.create(entry) : null;
      this.data.comms ??= [];
      const item = remote || {
        id: 'C-local-' + (globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)),
        ts: new Date().toISOString(),
        read: true,
        source: 'manual',
        ...entry,
      };
      if (!this.data.comms.some((entry) => entry.id === item.id)) this.data.comms.unshift(item);
      this.data.comms.sort((a, b) => (a.ts < b.ts ? 1 : -1));
      this.save('Коммуникация добавлена', entry.farmId || 'Неизвестный контакт', false);
      return item;
    },
    async markCommRead(id) {
      const c = this.data.comms.find((x) => x.id === id);
      if (c && !c.read) {
        c.read = true;
        c.updatedAt = new Date().toISOString();
        this.save('Прочитано сообщение', id, false);
        if (apiOn()) {
          try { await commsApi.markRead(id); this.commsSyncError = null; }
          catch (e) { this.commsSyncError = e.message; }
        }
      }
    },
    async markAllCommsRead() {
      this.data.comms.forEach((c) => (c.read = true));
      this.save('Отмечены прочитанными все сообщения', 'Коммуникации', false);
      if (apiOn()) {
        try { await commsApi.readAll(); this.commsSyncError = null; }
        catch (e) { this.commsSyncError = e.message; }
      }
    },
    async linkCommToFarm(commId, farmId) {
      const c = this.data.comms.find((x) => x.id === commId);
      if (c) {
        c.farmId = farmId;
        this.save('Коммуникация привязана к клиенту', `${commId} → ${farmId}`, false);
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
      try { localStorage.setItem(KEY, JSON.stringify(this.data)); } catch { /* noop */ }
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
        this.save('Ответ записан', commId, false);
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
      const synced = [...remote];
      for (const document of this.data.logistics) {
        if (!String(document.id).startsWith('LOC-')) continue;
        try {
          const saved = await logisticsApi.create({ ...document, clientId: document.id });
          if (!synced.some((entry) => entry.id === saved.id)) synced.push(saved);
        } catch {
          synced.push(document);
        }
      }
      synced.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
      this.data.logistics = synced;
      this.save('Документы логистики обновлены', 'Логистика', false);
      return true;
    },
    async addLogistics(payload) {
      this.data.logistics ??= [];
      const id = payload.clientId || this.uid('LOC');
      const item = await checkApi()
        ? await logisticsApi.create({ ...payload, clientId: id })
        : { ...payload, id, updatedAt: new Date().toISOString() };
      const index = this.data.logistics.findIndex((doc) => doc.id === item.id || doc.id === id);
      if (index >= 0) this.data.logistics.splice(index, 1, item);
      else this.data.logistics.unshift(item);
      this.save(payload.kind === 'dispatch' ? 'Создана выгрузка' : 'Создана поставка', item.number || item.id, false);
      return item;
    },
    async updateLogistics(id, payload) {
      const previous = (this.data.logistics || []).find((doc) => doc.id === id);
      if (!previous) throw new Error('Документ не найден.');
      const next = String(id).startsWith('LOC-')
        ? { ...previous, ...payload, id, updatedAt: new Date().toISOString() }
        : await logisticsApi.update(id, payload);
      const index = this.data.logistics.findIndex((doc) => doc.id === id);
      if (index >= 0) this.data.logistics.splice(index, 1, next);
      this.save('Документ логистики обновлён', next.number || id, false);
      return next;
    },
    async removeLogistics(id) {
      if (!String(id).startsWith('LOC-')) await logisticsApi.remove(id);
      this.data.logistics = (this.data.logistics || []).filter((d) => d.id !== id);
      this.save('Удалён документ логистики', id, false);
    },

    // ── Сквозной процесс: лид → квалификация → сделка → пилот → КП →
    // заказ → счёт → оплата → доставка → сопровождение (руководство v0.9 §3)
    uid(prefix) {
      return prefix + '-' + (globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2));
    },
    log(j, text) {
      j.history ??= [];
      j.history.unshift({ ts: new Date().toISOString(), text });
      j.history = j.history.slice(0, 60);
    },
    createJourneyFromLead(leadId) {
      const lead = this.data.leads.find((l) => l.id === leadId);
      if (!lead) return null;
      let j = (this.data.journeys || []).find((x) => x.leadId === leadId);
      if (!j) {
        j = {
          id: this.uid('J'), leadId, farmId: lead.farmId || null, dealId: null, pilotId: null,
          quoteId: null, orderId: null, invoiceId: null, shipmentId: null,
          stage: 'Квалификация', owner: lead.owner || 'Менеджер А', next: lead.next || null,
          createdAt: new Date().toISOString().slice(0, 10), qualification: null,
          history: [{ ts: new Date().toISOString(), text: `Маршрут создан из лида «${lead.name}»` }],
        };
        this.data.journeys ??= [];
        this.data.journeys.unshift(j);
        if (['Новый лид', 'Связаться'].includes(lead.status)) lead.status = 'В работе';
        this.save('Создан сквозной процесс', `${j.id} · ${lead.name}`);
      }
      return j;
    },
    saveQualification(journeyId, q) {
      const j = this.journeyById(journeyId);
      if (!j) return null;
      if (q.farmAction === 'link' && !this.farmById(q.farmId)) throw new Error('Выберите существующего контрагента.');
      if (q.farmAction === 'create' && !q.newFarmName?.trim()) throw new Error('Укажите название нового контрагента.');
      j.qualification = { ...q };
      // привязка/создание хозяйства (без дублей — сверять название и контакты)
      if (q.farmAction === 'link' && q.farmId) {
        j.farmId = q.farmId;
      } else if (q.farmAction === 'create' && q.newFarmName) {
        const f = {
          id: this.uid('F'), name: q.newFarmName.trim(), type: q.clientType || 'Клиент',
          region: q.region || '', crop: q.crop || '', area: Number(q.area) || 0,
          owner: j.owner, phone: q.phone || '', source: q.source || 'CRM',
          status: 'Активный', next: j.next || null, notes: q.note || 'Создано из сквозного процесса',
        };
        this.data.farms.push(f);
        j.farmId = f.id;
        this.log(j, `Создано хозяйство ${f.name} (${f.id})`);
      }
      if (q.contactName?.trim() && j.farmId) {
        const name = q.contactName.trim();
        const phone = (q.phone || '').replace(/\D/g, '');
        const contact = this.data.contacts.find((entry) => entry.farmId === j.farmId &&
          (phone ? (entry.phone || '').replace(/\D/g, '') === phone : entry.name?.toLowerCase() === name.toLowerCase()));
        const details = {
          name, phone: q.phone || contact?.phone || '', whatsapp: q.phone || contact?.whatsapp || '',
          telegram: q.telegram || contact?.telegram || '', email: q.email || contact?.email || '',
        };
        if (contact) Object.assign(contact, details);
        else this.data.contacts.push({
          id: this.uid('CT'), farmId: j.farmId, ...details,
          primary: !this.data.contacts.some((entry) => entry.farmId === j.farmId && entry.primary),
        });
      }
      const lead = this.data.leads.find((l) => l.id === j.leadId);
      if (lead) {
        if (!j.dealId) lead.status = 'Квалифицирован';
        if (j.farmId) lead.farmId = j.farmId;
      }
      if (j.stage === 'Квалификация') j.stage = 'Сделка';
      this.log(j, `Квалификация сохранена: ${q.clientType}` + (j.farmId ? `, хозяйство ${j.farmId}` : ''));
      this.save('Квалификация лида', journeyId);
      return j;
    },
    createDealFromJourney(journeyId, { volumeL, amount }) {
      const j = this.journeyById(journeyId);
      if (!j) return null;
      const existing = this.dealById(j.dealId);
      if (existing) return existing;
      const lead = this.data.leads.find((l) => l.id === j.leadId);
      const farm = j.farmId ? this.farmById(j.farmId) : null;
      const d = {
        id: this.uid('D'), title: `${farm?.name || lead?.name || 'Сделка'} — поставка BIOTORF`,
        farmId: j.farmId, stage: 'Пилот или КП', amount: Number(amount) || 0,
        volumeL: Number(volumeL) || 0, owner: j.owner, next: j.next || null, journeyId: j.id,
      };
      this.data.deals.push(d);
      j.dealId = d.id;
      j.stage = 'Пилот или КП';
      if (lead) lead.status = 'Сделка создана';
      this.log(j, `Создана сделка ${d.id}: ${volumeL} л · ${amount} сом`);
      this.save('Создана сделка из маршрута', `${j.id} → ${d.id}`);
      return d;
    },
    createPilotFromJourney(journeyId, p) {
      const j = this.journeyById(journeyId);
      if (!j) return null;
      const existing = this.pilotById(j.pilotId);
      if (existing) return existing;
      const rec = {
        id: this.uid('P'), farmId: j.farmId, dealId: j.dealId, journeyId: j.id,
        crop: p.crop || '', area: Number(p.area) || 0, control: p.control || '',
        goal: p.goal || '', status: 'Запланирован', date: p.date || null,
        applications: [], result: null,
      };
      this.data.pilots.push(rec);
      j.pilotId = rec.id;
      j.stage = 'Пилот идёт';
      this.log(j, `Создан пилот ${rec.id}: ${rec.crop}, ${rec.area} га`);
      this.save('Создан пилот из маршрута', `${j.id} → ${rec.id}`);
      return rec;
    },
    createQuoteFromJourney(journeyId, q) {
      const j = this.journeyById(journeyId);
      if (!j) return null;
      if (!this.dealById(j.dealId)) throw new Error('Сначала создайте сделку.');
      if (this.orderById(j.orderId)) throw new Error('Из этого предложения уже оформлен заказ.');
      const items = (q.items || []).map((it) => {
        const sku = this.skuById(it.sku);
        const packs = Number(it.packs);
        const price = Number(it.price);
        const pack = Number(sku?.pack);
        if (!sku || !Number.isSafeInteger(packs) || packs < 1 || !Number.isFinite(price) || price <= 0 || !Number.isFinite(pack) || pack <= 0) {
          throw new Error('Для каждой позиции выберите товар с фасовкой, укажите целое количество упаковок и цену больше нуля.');
        }
        return { sku: sku.id, name: sku.name, pack, packs, unit: 'шт.', liters: packs * pack, price, sum: Math.round(packs * price * 100) / 100 };
      });
      if (!items.length) throw new Error('Добавьте хотя бы одну позицию в КП.');
      const total = Math.round(items.reduce((sum, item) => sum + item.sum, 0) * 100) / 100;
      const quote = {
        id: this.uid('Q'), journeyId, dealId: j.dealId, farmId: j.farmId,
        number: 'КП-' + String(Date.now()).slice(-6), date: q.date || new Date().toISOString().slice(0, 10),
        items, terms: q.terms || '', total, status: 'Черновик',
      };
      this.data.quotes ??= [];
      this.data.quotes.unshift(quote);
      j.quoteId = quote.id;
      j.stage = 'Пилот или КП';
      const deal = j.dealId ? this.dealById(j.dealId) : null;
      if (deal) deal.amount = total;
      this.log(j, `Создано КП ${quote.number} на ${total} сом`);
      this.save('Создано КП', `${j.id} → ${quote.id}`);
      return quote;
    },
    markQuoteSent(journeyId) {
      const journey = this.journeyById(journeyId);
      const quote = journey && this.quoteById(journey.quoteId);
      if (!quote || quote.status !== 'Черновик') return quote;
      quote.status = 'Отправлено';
      journey.stage = 'КП отправлено';
      const deal = this.dealById(journey.dealId);
      if (deal) deal.stage = 'КП отправлено';
      this.log(journey, `Отмечена отправка КП ${quote.number}`);
      this.save('Отмечена отправка КП', quote.id);
      return quote;
    },
    confirmOrderFromQuote(journeyId) {
      const j = this.journeyById(journeyId);
      const quote = j && this.quoteById(j.quoteId);
      if (!quote) return null;
      const existing = this.orderById(j.orderId) || this.data.orders.find((record) => record.quoteId === quote.id);
      if (existing) return { order: existing, invoice: this.data.invoices.find((invoice) => invoice.orderId === existing.id) };
      if (!['Отправлено', 'Принят'].includes(quote.status)) throw new Error('Сначала отправьте КП и отметьте отправку.');
      if (!Array.isArray(quote.items) || !quote.items.length || !Number.isFinite(Number(quote.total)) || Number(quote.total) <= 0) {
        throw new Error('Проверьте позиции и сумму КП перед подтверждением заказа.');
      }
      const order = {
        id: this.uid('O'), number: 'З-' + quote.id.slice(-8), farmId: j.farmId, journeyId: j.id,
        dealId: j.dealId, quoteId: quote.id, date: new Date().toISOString().slice(0, 10),
        items: quote.items.map((item) => ({ ...item })), amount: Number(quote.total), status: 'Подтверждён',
      };
      const plans = this.autoProductionFromOrder(order);
      this.data.orders.push(order);
      quote.status = 'Принят';
      const deal = this.dealById(j.dealId);
      if (deal) deal.stage = 'Счёт выставлен';
      const inv = {
        id: this.uid('INV'), number: 'СЧ-' + quote.id.slice(-8), farmId: j.farmId,
        dealId: j.dealId, orderId: order.id, journeyId: j.id, date: order.date, amount: order.amount,
        status: 'Выставлен', paid: false,
      };
      this.data.invoices.unshift(inv);
      j.orderId = order.id; j.invoiceId = inv.id; j.stage = 'Счёт выставлен';
      this.log(j, `Заказ ${order.number} подтверждён, счёт ${inv.number} выставлен, позиций в плане: ${plans.length}`);
      this.save('Заказ и счёт из КП', `${j.id} → ${order.id}`);
      return { order, invoice: inv };
    },
    autoProductionFromOrder(order) {
      this.data.production ??= [];
      const existing = this.data.production.filter((record) => record.orderId === order.id);
      if (existing.length) return existing;
      const demand = new Map();
      for (const item of order.items || []) {
        const sku = this.skuById(item?.sku);
        const qty = Number(item?.packs ?? item?.qty);
        const pack = Number(item?.pack ?? sku?.pack);
        if (!item?.sku || !Number.isSafeInteger(qty) || qty <= 0 || !Number.isFinite(pack) || pack <= 0) {
          throw new Error('В заказе у каждой позиции должны быть артикул, фасовка и количество упаковок.');
        }
        const planned = demand.get(item.sku) || { sku: item.sku, name: item.name || sku?.name || item.sku, qty: 0, volume: 0 };
        planned.qty += qty;
        planned.volume += qty * pack;
        demand.set(item.sku, planned);
      }
      const plans = [...demand.values()].map((item) => ({
        id: this.uid('PLAN'), date: order.date,
        sku: item.sku, product: item.name, qty: item.qty, unit: 'шт.',
        plannedVolumeL: Math.round(item.volume * 1000) / 1000,
        status: 'План', orderId: order.id,
        notes: 'Потребность заказа. Перед запуском проверьте остаток готового товара и доступность пасты.',
      }));
      this.data.production.unshift(...plans);
      return plans;
    },
    markInvoicePaid(invoiceId) {
      const inv = this.invoiceById(invoiceId);
      if (!inv || inv.paid || inv.status === 'Оплачен') return inv;
      if (!Number.isFinite(Number(inv.amount)) || Number(inv.amount) <= 0) throw new Error('Проверьте сумму счёта.');
      const balance = this.invoiceBalance(inv);
      if (balance > 0) {
        this.data.payments.unshift({
          id: this.uid('PAY'), invoiceId, orderId: inv.orderId, date: new Date().toISOString().slice(0, 10),
          amount: balance, method: 'Ручное подтверждение',
        });
      }
      inv.paid = true; inv.status = 'Оплачен';
      inv.paidAt = new Date().toISOString().slice(0, 10);
      const j = inv.journeyId ? this.journeyById(inv.journeyId) : null;
      if (j) { j.stage = 'Оплачено'; this.log(j, `Оплата по счёту ${inv.number} подтверждена вручную (v0.9: без банковской связи)`); }
      const deal = j?.dealId ? this.dealById(j.dealId) : null;
      if (deal) deal.stage = 'Оплачено';
      this.save('Подтверждена оплата', inv.number);
      return inv;
    },
    createShipmentFromJourney(journeyId, s) {
      const j = this.journeyById(journeyId);
      if (!j) return null;
      const order = j.orderId ? this.orderById(j.orderId) : null;
      const existing = this.data.shipments.find((record) => record.id === j.shipmentId);
      if (existing) return existing;
      if (!order) throw new Error('Сначала оформите заказ.');
      const invoice = this.invoiceById(j.invoiceId);
      if (!invoice || (!invoice.paid && invoice.status !== 'Оплачен')) throw new Error('Сначала подтвердите оплату счёта.');
      const sh = {
        id: this.uid('SH'), number: 'ОТ-' + order.id.slice(-8), journeyId: j.id,
        farmId: j.farmId, orderId: j.orderId, date: new Date().toISOString().slice(0, 10),
        planDate: s.planDate || null, carrier: s.carrier || '', vehicle: s.vehicle || '', driver: s.driver || '',
        items: (order?.items || []).map((item) => ({ ...item })), amount: order?.amount || 0,
        status: 'Запланирована', received: false, actId: null,
      };
      this.data.shipments ??= [];
      this.data.shipments.unshift(sh);
      j.shipmentId = sh.id; j.stage = 'Доставка';
      const deal = j.dealId ? this.dealById(j.dealId) : null;
      if (deal) deal.stage = 'Доставка';
      this.log(j, `Создана отгрузка ${sh.number}, план ${sh.planDate || '—'}, перевозчик ${sh.carrier || '—'}`);
      this.save('Создана отгрузка', `${j.id} → ${sh.id}`);
      return sh;
    },
    confirmShipmentReceived(shipmentId, { nextTask, nextDate } = {}) {
      const sh = (this.data.shipments || []).find((x) => x.id === shipmentId);
      if (!sh || sh.received) return sh;
      sh.received = true; sh.status = 'Получено клиентом';
      sh.receivedAt = new Date().toISOString().slice(0, 10);
      const j = sh.journeyId ? this.journeyById(sh.journeyId) : null;
      if (j) { j.stage = 'Сопровождение'; j.next = nextDate || j.next; this.log(j, 'Доставка подтверждена клиентом'); }
      const deal = j?.dealId ? this.dealById(j.dealId) : null;
      if (deal) deal.stage = 'Получено клиентом';
      const order = this.orderById(sh.orderId);
      if (order) order.status = 'Отгружен';
      if (nextTask) {
        this.addTask({ title: nextTask, owner: j?.owner || 'Менеджер А', due: nextDate || null, priority: 'Средний', refKind: 'journey', refId: j?.id || null, status: 'Открыта' });
        if (j) this.log(j, `Поставлена следующая задача «${nextTask}»`);
      }
      this.save('Подтверждено получение отгрузки', sh.number);
      return sh;
    },
    addTask(t) {
      const rec = { id: this.uid('T'), status: 'Открыта', createdAt: new Date().toISOString(), ...t };
      this.data.tasks.unshift(rec);
      this.save('Создана задача', rec.title);
      return rec;
    },
    updateTask(id, patch) {
      const t = this.data.tasks.find((x) => x.id === id);
      if (t) { Object.assign(t, patch); this.save('Задача обновлена', t.title); }
      return t;
    },
    setJourneyNext(journeyId, { result, owner, due }) {
      const j = this.journeyById(journeyId);
      if (!j) return null;
      j.next = due || j.next;
      if (owner) j.owner = owner;
      this.log(j, `Следующее действие: ${result}` + (due ? ` (до ${due})` : ''));
      if (result) {
        this.addTask({ title: result, owner: owner || j.owner, due: due || null, priority: 'Средний', refKind: 'journey', refId: j.id, status: 'Открыта' });
      }
      this.save('Следующее действие маршрута', journeyId);
      return j;
    },
    setJourneyStage(journeyId, stage) {
      const j = this.journeyById(journeyId);
      if (j) { j.stage = stage; this.log(j, `Стадия маршрута изменена на «${stage}»`); this.save('Стадия маршрута', journeyId); }
      return j;
    },
    editEntity(kind, id, patch) {
      const maps = { task: 'tasks', deal: 'deals', lead: 'leads', farm: 'farms', pilot: 'pilots', order: 'orders', invoice: 'invoices', shipment: 'shipments', quote: 'quotes' };
      const coll = this.data[maps[kind]];
      const rec = coll?.find((x) => x.id === id);
      if (!rec) return null;
      Object.assign(rec, patch);
      this.save(`Изменён объект (${kind})`, id);
      return rec;
    },
    addClientNote(farmId, text) {
      this.data.clientNotes ??= [];
      this.data.clientNotes.unshift({ id: this.uid('N'), farmId, ts: new Date().toISOString(), text });
      this.save('Заметка клиента', farmId);
    },
    addContact(farmId, c) {
      this.data.contacts ??= [];
      const rec = { id: this.uid('CT'), farmId, primary: false, ...c };
      this.data.contacts.push(rec);
      const f = this.farmById(farmId);
      if (f && c.phone && !f.phone) f.phone = c.phone;
      this.save('Добавлен контакт', farmId);
      return rec;
    },

    save(action = 'Изменены данные', object = 'Система', sync = true) {
      this.data.audit ??= [];
      this.data.audit.unshift({ time: new Date().toISOString(), action, object });
      this.data.audit = this.data.audit.slice(0, 300);
      if (sync) captureChanges(this.crmSync, this.data, SYNC_COLLECTIONS);
      this.persistCrmCache();
      if (sync) this.queueCrmSync();
    },
    persistCrmCache() {
      persistPending(this.crmSync);
      try { localStorage.setItem(KEY, JSON.stringify(this.data)); } catch { /* storage disabled */ }
    },

    // ── Синхронизация CRM-состояния с сервером (backend /api/crm/state) ──

    // ── Наполнение таблиц: CSV/JSON-импорт и очистка ───────────────────
    // Вызывается из UI («Импорт» в табличных разделах). records — массив
    // объектов [{col: value}]; заголовки CSV используются как имена полей.
    parseCsv(text, delimiter) {
      const rows = [];
      let row = [], field = '', inQ = false;
      for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (inQ) {
          if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
          else if (ch === '"') inQ = false;
          else field += ch;
        } else if (ch === '"') inQ = true;
        else if (ch === delimiter) { row.push(field); field = ''; }
        else if (ch === '\n' || ch === '\r') {
          if (ch === '\r' && text[i + 1] === '\n') i++;
          row.push(field); field = '';
          if (row.some((c) => c.trim() !== '')) rows.push(row);
          row = [];
        } else field += ch;
      }
      row.push(field);
      if (row.some((c) => c.trim() !== '')) rows.push(row);
      return rows;
    },
    csvToRecords(csvText) {
      const text = String(csvText || '').replace(/^\uFEFF/, '');
      const commaRows = this.parseCsv(text, ',');
      const semicolonRows = this.parseCsv(text, ';');
      const rows = (semicolonRows[0]?.length ?? 0) > (commaRows[0]?.length ?? 0)
        ? semicolonRows : commaRows;
      if (!rows.length) return [];
      const headers = rows[0].map((h) => h.trim());
      if (headers.some((h) => !h) || new Set(headers).size !== headers.length) {
        throw new Error('В CSV есть пустые или повторяющиеся заголовки');
      }
      return rows.slice(1).map((r) => {
        if (r.length !== headers.length) {
          throw new Error('Количество значений в строке CSV не совпадает с числом заголовков');
        }
        return Object.fromEntries(headers.map((h, i) => [h, r[i].trim()]));
      }).filter((o) => Object.values(o).some((v) => v !== ''));
    },
    async importCollection(coll, records, mode = 'merge') {
      if (!SYNC_COLLECTIONS.includes(coll)) throw new Error('Неизвестная таблица: ' + coll);
      if (!Array.isArray(records) || !records.length) throw new Error('Пустой набор данных для импорта');
      const prepared = records.map((raw) => {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
          throw new Error('Каждая строка импорта должна быть объектом');
        }
        const { _updatedAt, _delete, ...rec } = raw;
        return { ...rec, id: String(rec.id ?? '').trim() || this.uid(coll) };
      });
      if (new Set(prepared.map((row) => row.id)).size !== prepared.length) {
        throw new Error('В файле есть повторяющиеся ID');
      }
      return serializeCrm(this.crmSync, async () => {
        if (!apiOn() && mode === 'replace') throw new Error('Для замены таблицы требуется подключение к серверу.');
        const pending = this.crmSync.pending[coll];
        if (apiOn() && (mode === 'replace' ? pending.size : prepared.some((row) => pending.has(row.id)))) {
          await this.flushCrmChanges();
        }
        const response = apiOn() ? await crmApi.importCollection(coll, prepared, mode) : null;
        const rows = new Map((mode === 'replace' ? [] : this.data[coll] || []).map((row) => [String(row.id), row]));
        let created = 0, updated = 0;
        for (const row of response?.records || prepared) {
          const { _expectedRev, ...record } = row;
          const existing = rows.get(record.id);
          if (existing) updated++;
          else created++;
          rows.set(record.id, { ...existing, ...record });
        }
        if (response) acceptCrmState(this.crmSync, this.data, { [coll]: [...rows.values()] }, [coll]);
        else this.data[coll] = [...rows.values()];
        this.save(`Импорт ${coll}: +${created}/${updated}`, coll, !response);
        return response || { created, updated, total: rows.size };
      });
    },
    async deleteRow(coll, id) {
      if (!SYNC_COLLECTIONS.includes(coll)) throw new Error('Неизвестная таблица: ' + coll);
      return serializeCrm(this.crmSync, async () => {
        const online = apiOn();
        if (online) {
          if (this.crmSync.pending[coll].has(String(id))) await this.flushCrmChanges();
          const record = this.data[coll]?.find((row) => row.id === id);
          await crmApi.remove(coll, id, record?._updatedAt);
        }
        this.data[coll] = (this.data[coll] || []).filter((row) => row.id !== id);
        if (online) this.crmSync.baseline[coll].delete(String(id));
        else captureChanges(this.crmSync, this.data, [coll], true);
        this.save(`Удалена запись ${id} (${coll})`, coll, false);
        if (!online) this.queueCrmSync();
        return true;
      });
    },
    async importCsvFile(coll, file, mode = 'merge') {
      const text = await file.text();
      return this.importCollection(coll, this.csvToRecords(text), mode);
    },
    async refreshListOptions() {
      if (!apiOn() && !(await checkApi())) return;
      const shared = await crmApi.getOptions();
      const defaults = emptyState().lists;
      const pending = {};
      for (const [key, values] of Object.entries(this.data.lists || {})) {
        const known = new Set([...(defaults[key] || []), ...(shared[key] || [])].map((v) => v.toLowerCase()));
        const local = values.filter((v) => v.trim() && v.length <= 500 && !known.has(v.trim().toLowerCase()));
        if (local.length) pending[key] = local;
      }
      this.mergeListOptions(Object.keys(pending).length ? await crmApi.addOptions(pending) : shared);
    },
    async addListItem(listKey, value) {
      if (!apiOn() && !(await checkApi())) throw new Error('Сервер недоступен. Значение не сохранено в общем справочнике.');
      const shared = await crmApi.addOptions({ [listKey]: [value] });
      this.mergeListOptions(shared);
      return shared[listKey].find((v) => v.toLowerCase() === value.toLowerCase()) || value;
    },
    mergeListOptions(shared) {
      this.data.lists ??= {};
      for (const [key, values] of Object.entries(shared)) {
        const merged = new Map([...(this.data.lists[key] || []), ...values].map((v) => [v.toLowerCase(), v]));
        this.data.lists[key] = [...merged.values()];
      }
      try { localStorage.setItem(KEY, JSON.stringify(this.data)); } catch { /* noop */ }
    },
    // Список для модалки: справочник + все уникальные значения из существующих записей
    optionsFor(listKey, coll, field) {
      const set = new Set(this.data.lists?.[listKey] || []);
      for (const rec of this.data[coll] || []) {
        const v = rec?.[field];
        if (typeof v === 'string' && v.trim()) set.add(v.trim());
      }
      return [...set].sort((a, b) => a.localeCompare(b, 'ru'));
    },
    async wipeCollection(coll) {
      if (!SYNC_COLLECTIONS.includes(coll)) throw new Error('Неизвестная таблица: ' + coll);
      return serializeCrm(this.crmSync, async () => {
        if (!apiOn()) throw new Error('Для очистки таблицы требуется подключение к серверу.');
        if (this.crmSync.pending[coll].size) await this.flushCrmChanges();
        const response = await crmApi.wipeCollection(coll);
        acceptCrmState(this.crmSync, this.data, { [coll]: [] }, [coll]);
        this.save(`Очищена таблица ${coll} (${response.removed} записей)`, coll, false);
        return response;
      });
    },

    queueCrmSync() {
      if (!hasCrmChanges(this.crmSync)) return;
      if (!apiOn()) {
        this.crmSyncError = 'Изменения сохранены в браузере и ожидают подключения к серверу.';
        return;
      }
      if (this._crmSyncTimer) clearTimeout(this._crmSyncTimer);
      this._crmSyncTimer = setTimeout(() => {
        this._crmSyncTimer = null;
        this.pushCrmState().catch(() => {});
      }, 500);
    },
    async flushCrmChanges() {
      const changes = crmPayload(this.crmSync);
      if (!Object.keys(changes).length) return;
      try {
        if (!apiOn() && !(await checkApi())) throw new Error('Сервер недоступен');
        if (!this.crmSync.supportsDelta) {
          this.crmSync.supportsDelta = (await crmApi.getState())._delta === true;
          if (!this.crmSync.supportsDelta) throw new Error('На сервере нужна новая версия CRM');
        }
        const state = await crmApi.putState({ ...changes, _delta: true });
        if (state._delta !== true) throw new Error('На сервере нужна новая версия CRM');
        acceptCrmState(this.crmSync, this.data, state, SYNC_COLLECTIONS, changes);
        this.crmSyncError = null;
        this.serverOnline = true;
        this.persistCrmCache();
      } catch (error) {
        this.crmSyncError = `${error.message}. Изменения сохранены в браузере.`;
        throw error;
      }
    },
    pushCrmState() {
      return serializeCrm(this.crmSync, () => this.flushCrmChanges());
    },
    retryCrmSync() {
      return hasCrmChanges(this.crmSync) ? this.pushCrmState() : this.pullCrmState();
    },
    pullCrmState({ discardPending = false } = {}) {
      return serializeCrm(this.crmSync, async () => {
        if (!(await checkApi())) {
          this.serverOnline = false;
          if (hasCrmChanges(this.crmSync)) this.queueCrmSync();
          return false;
        }
        this.serverOnline = true;
        try {
          const state = await crmApi.getState();
          this.crmSync.supportsDelta = state._delta === true;
          if (discardPending) for (const changes of Object.values(this.crmSync.pending)) changes.clear();
          acceptCrmState(this.crmSync, this.data, state, SYNC_COLLECTIONS);
          this.crmSyncError = null;
          this.persistCrmCache();
          if (!discardPending) this.queueCrmSync();
          return true;
        } catch (error) {
          this.crmSyncError = error.message;
          return false;
        }
      });
    },
    reset() {
      this.data = emptyState();
      for (const changes of Object.values(this.crmSync.pending)) changes.clear();
      this.crmSync.baseline = snapshot(this.data, SYNC_COLLECTIONS);
      this.persistCrmCache();
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
