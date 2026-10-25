import { defineStore } from 'pinia';
import { SAMPLE } from '@/data/sample';
import { commsApi, apiEnabled, checkApi } from '@/api/commsClient';
import { logisticsApi } from '@/api/logisticsClient';
import { crmApi } from '@/api/crmClient';

// apiEnabled — функция (см. commsClient.js); вызываем как функцию
const apiOn = () => typeof apiEnabled === 'function' ? apiEnabled() : !!apiEnabled;

const KEY = 'biotorf-business-os-mvp-2026-10';

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
    return structuredClone(SAMPLE);
  }
}

export const useDbStore = defineStore('db', {
  state: () => ({ data: load(), commsSyncError: null, crmSyncError: null, serverOnline: false }),
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

    // ── Сквозной процесс: лид → квалификация → сделка → пилот → КП →
    // заказ → счёт → оплата → доставка → сопровождение (руководство v0.9 §3)
    uid(prefix) { return prefix + '-' + String(Date.now()).slice(-9); },
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
      j.qualification = { ...q };
      // привязка/создание хозяйства (без дублей — сверять название и контакты)
      if (q.farmAction === 'link' && q.farmId) {
        j.farmId = q.farmId;
      } else if (q.farmAction === 'create' && q.newFarmName) {
        const f = {
          id: this.uid('F'), name: q.newFarmName, type: q.clientType || 'Клиент',
          region: q.region || '', crop: q.crop || '', area: Number(q.area) || 0,
          owner: j.owner, phone: q.phone || '', source: q.source || 'CRM',
          status: 'Активный', next: j.next || null, note: q.note || 'Создано из сквозного процесса',
        };
        this.data.farms.push(f);
        j.farmId = f.id;
        this.log(j, `Создано хозяйство ${f.name} (${f.id})`);
      }
      if (q.contactName && j.farmId) {
        this.data.contacts.push({
          id: this.uid('CT'), farmId: j.farmId, name: q.contactName,
          phone: q.phone || '', whatsapp: q.phone || '', telegram: q.telegram || '',
          email: q.email || '', primary: true,
        });
      }
      const lead = this.data.leads.find((l) => l.id === j.leadId);
      if (lead) { lead.status = 'Квалифицирован'; if (j.farmId) lead.farmId = j.farmId; }
      j.stage = 'Сделка';
      this.log(j, `Квалификация сохранена: ${q.clientType}` + (j.farmId ? `, хозяйство ${j.farmId}` : ''));
      this.save('Квалификация лида', journeyId);
      return j;
    },
    createDealFromJourney(journeyId, { volumeL, amount }) {
      const j = this.journeyById(journeyId);
      if (!j) return null;
      const lead = this.data.leads.find((l) => l.id === j.leadId);
      const farm = j.farmId ? this.farmById(j.farmId) : null;
      const d = {
        id: this.uid('D'), title: `${farm?.name || lead?.name || 'Сделка'} — поставка BIOTORF`,
        farmId: j.farmId, stage: 'КП отправлено', amount: Number(amount) || 0,
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
      const items = (q.items || []).filter((it) => it.sku && Number(it.packs) > 0)
        .map((it) => {
          const sku = this.skuById(it.sku);
          const packs = Number(it.packs) || 0, price = Number(it.price) || 0;
          return { sku: it.sku, name: sku.name || it.sku, pack: sku.pack || 1, packs, liters: packs * (sku.pack || 1), price, sum: packs * price };
        });
      const total = items.reduce((s, it) => s + it.sum, 0);
      const quote = {
        id: this.uid('Q'), journeyId, dealId: j.dealId, farmId: j.farmId,
        number: 'КП-' + String(Date.now()).slice(-6), date: q.date || new Date().toISOString().slice(0, 10),
        items, terms: q.terms || '', total, status: 'Отправлено',
      };
      this.data.quotes ??= [];
      this.data.quotes.unshift(quote);
      j.quoteId = quote.id;
      j.stage = 'КП отправлено';
      const deal = j.dealId ? this.dealById(j.dealId) : null;
      if (deal) { deal.stage = 'КП отправлено'; deal.amount = total || deal.amount; }
      this.log(j, `Создано КП ${quote.number} на ${total} сом`);
      this.save('Создано КП', `${j.id} → ${quote.id}`);
      return quote;
    },
    confirmOrderFromQuote(journeyId) {
      const j = this.journeyById(journeyId);
      if (!j || !j.quoteId) return null;
      const quote = this.quoteById(j.quoteId);
      if (!quote) return null;
      // позиции и сумма переносятся из КП (демонстрационный перенос без проводок)
      const order = {
        id: this.uid('O'), num: 'З-' + String(Date.now()).slice(-6), farmId: j.farmId, journeyId: j.id, quoteId: quote.id,
        date: new Date().toISOString().slice(0, 10),
        items: structuredClone(quote.items), amount: quote.total, status: 'Подтверждён',
      };
      this.data.orders.push(order);
      quote.status = 'Принят';
      const deal = j.dealId ? this.dealById(j.dealId) : null;
      if (deal) deal.stage = 'Счет/договор';
      const inv = {
        id: this.uid('INV'), number: 'СЧ-' + String(Date.now()).slice(-6), farmId: j.farmId,
        orderId: order.id, journeyId: j.id, date: order.date, amount: order.amount,
        status: 'Выставлен', paid: false,
      };
      this.data.invoices ??= [];
      this.data.invoices.unshift(inv);
      j.orderId = order.id; j.invoiceId = inv.id; j.stage = 'Счёт выставлен';
      this.log(j, `Заказ ${order.id} подтверждён из КП, счёт ${inv.number} выставлен`);
      this.save('Заказ и счёт из КП', `${j.id} → ${order.id}`);
      return { order, invoice: inv };
    },
    markInvoicePaid(invoiceId) {
      const inv = this.invoiceById(invoiceId);
      if (!inv) return null;
      inv.paid = true; inv.status = 'Оплачен';
      inv.paidAt = new Date().toISOString().slice(0, 10);
      this.data.payments ??= [];
      this.data.payments.unshift({ id: this.uid('PAY'), invoiceId, date: inv.paidAt, amount: inv.amount, method: 'Наличные/ручное подтверждение' });
      const j = inv.journeyId ? this.journeyById(inv.journeyId) : null;
      if (j) { j.stage = 'Оплачено'; this.log(j, `Оплата по счёту ${inv.number} подтверждена вручную (v0.9: без банковской связи)`); }
      const deal = j?.dealId ? this.dealById(j.dealId) : null;
      if (deal) deal.stage = 'Оплачено';
      const order = inv.orderId ? this.orderById(inv.orderId) : null;
      if (order) order.status = 'Оплачен';
      this.save('Подтверждена оплата (демо)', inv.number);
      return inv;
    },
    createShipmentFromJourney(journeyId, s) {
      const j = this.journeyById(journeyId);
      if (!j) return null;
      const order = j.orderId ? this.orderById(j.orderId) : null;
      const sh = {
        id: this.uid('SH'), number: 'ОТ-' + String(Date.now()).slice(-6), journeyId: j.id,
        farmId: j.farmId, orderId: j.orderId, date: new Date().toISOString().slice(0, 10),
        planDate: s.planDate || null, carrier: s.carrier || '', vehicle: s.vehicle || '', driver: s.driver || '',
        items: order ? structuredClone(order.items) : [], amount: order?.amount || 0,
        status: 'Запланирована', received: false, actId: null,
      };
      this.data.shipments ??= [];
      this.data.shipments.unshift(sh);
      j.shipmentId = sh.id; j.stage = 'Доставка';
      const deal = j.dealId ? this.dealById(j.dealId) : null;
      if (deal) deal.stage = 'Отгружено';
      this.log(j, `Создана отгрузка ${sh.number}, план ${sh.planDate || '—'}, перевозчик ${sh.carrier || '—'}`);
      this.save('Создана отгрузка', `${j.id} → ${sh.id}`);
      return sh;
    },
    confirmShipmentReceived(shipmentId, { nextTask, nextDate } = {}) {
      const sh = (this.data.shipments || []).find((x) => x.id === shipmentId);
      if (!sh) return null;
      sh.received = true; sh.status = 'Получено клиентом';
      sh.receivedAt = new Date().toISOString().slice(0, 10);
      const j = sh.journeyId ? this.journeyById(sh.journeyId) : null;
      if (j) { j.stage = 'Сопровождение'; j.next = nextDate || j.next; this.log(j, 'Доставка подтверждена клиентом'); }
      const deal = j?.dealId ? this.dealById(j.dealId) : null;
      if (deal) deal.stage = 'Получено клиентом';
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

    save(action = 'Изменены данные', object = 'Система') {
      this.data.audit ??= [];
      this.data.audit.unshift({ time: new Date().toISOString(), action, object });
      this.data.audit = this.data.audit.slice(0, 300);
      try {
        localStorage.setItem(KEY, JSON.stringify(this.data));
      } catch {
        console.warn('localStorage full');
      }
      // фоновая синхронизация с бэкендом (если доступен) — общая база для всех
      this.queueCrmSync();
    },

    // ── Синхронизация CRM-состояния с сервером (backend /api/crm/state) ──
    queueCrmSync() {
      if (!apiOn()) return;
      if (this._crmSyncTimer) clearTimeout(this._crmSyncTimer);
      this._crmSyncTimer = setTimeout(() => {
        this._crmSyncTimer = null;
        this.pushCrmState().catch(() => { this.crmSyncError = 'Сервер недоступен — данные сохранены локально'; });
      }, 1200);
    },
    async pushCrmState() {
      const payload = { _syncAt: new Date().toISOString() };
      for (const coll of SYNC_COLLECTIONS) payload[coll] = this.data[coll] || [];
      const state = await crmApi.putState(payload);
      // принимаем разрешённые сервером версии записей (lastWriteWins)
      for (const coll of SYNC_COLLECTIONS) {
        if (Array.isArray(state[coll])) this.data[coll] = state[coll].map((r) => ({ ...r, _updatedAt: undefined }));
      }
      this.crmSyncError = null;
      this.serverOnline = true;
      try { localStorage.setItem(KEY, JSON.stringify(this.data)); } catch { /* noop */ }
      return state;
    },
    async pullCrmState() {
      // первичная загрузка: сервер пустой — засеем демо; сервер с данными — берём его
      if (!(await checkApi())) { this.serverOnline = false; return false; }
      this.serverOnline = true;
      try {
        let state = await crmApi.getState();
        const empty = SYNC_COLLECTIONS.every((c) => !(state[c] || []).length);
        if (empty) {
          await crmApi.seed(Object.fromEntries(SYNC_COLLECTIONS.map((c) => [c, this.data[c] || []])));
          state = await crmApi.getState();
        }
        for (const coll of SYNC_COLLECTIONS) {
          if (Array.isArray(state[coll])) this.data[coll] = state[coll];
        }
        this.crmSyncError = null;
        try { localStorage.setItem(KEY, JSON.stringify(this.data)); } catch { /* noop */ }
        return true;
      } catch (e) {
        this.crmSyncError = e.message;
        return false;
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