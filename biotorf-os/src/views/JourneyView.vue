<script setup>
// «Сквозной процесс» — главный сценарий менеджера по руководству v0.9 §3:
// лид → квалификация → сделка → пилот (если нужен) → КП → заказ → счёт →
// оплата → доставка → сопровождение.
import { ref, computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const ui = useUiStore();
const { money, day, num } = useFormatters();

const CLIENT_TYPES = ['Агропроизводитель', 'Розничный магазин', 'Оптовая база', 'Дилер', 'Дистрибьютор', 'Другой'];
const SOURCES = ['Instagram', 'Telegram', 'WhatsApp', 'Звонок', 'Мероприятие', 'Рекомендация', 'Сайт', 'Другое'];
const STAGES = ['Квалификация', 'Сделка', 'Пилот или КП', 'КП отправлено', 'Счёт выставлен', 'Оплачено', 'Доставка', 'Сопровождение', 'Завершено'];

const selectedId = ref(ui.activeWork?.kind === 'journey' ? ui.activeWork.id : null);
const journeys = computed(() => db.journeys);
const journey = computed(() => selectedId.value ? db.journeyById(selectedId.value) : null);
const lead = computed(() => journey.value ? db.data.leads.find((l) => l.id === journey.value.leadId) : null);
const farm = computed(() => journey.value?.farmId ? db.farmById(journey.value.farmId) : null);
const deal = computed(() => journey.value?.dealId ? db.dealById(journey.value.dealId) : null);
const pilot = computed(() => journey.value?.pilotId ? db.pilotById(journey.value.pilotId) : null);
const quote = computed(() => journey.value?.quoteId ? db.quoteById(journey.value.quoteId) : null);
const order = computed(() => journey.value?.orderId ? db.orderById(journey.value.orderId) : null);
const invoice = computed(() => journey.value?.invoiceId ? db.invoiceById(journey.value.invoiceId) : null);
const shipment = computed(() => journey.value?.shipmentId ? db.shipments.find((s) => s.id === journey.value.shipmentId) : null);
const isAgro = computed(() => journey.value?.qualification?.clientType === 'Агропроизводитель');
const stageIdx = computed(() => Math.max(0, STAGES.indexOf(journey.value?.stage || 'Квалификация')));

function pick(id) { selectedId.value = id; ui.activeWork = { kind: 'journey', id }; }

const newLeadOpen = ref(false);
const newLead = ref({ name: '', contactName: '', phone: '', company: '', region: '', source: 'WhatsApp', owner: 'Менеджер А', next: '' });
function createLead() {
  if (!newLead.value.name.trim()) return;
  const leadRec = {
    id: db.uid('L'), name: newLead.value.name.trim(), farmId: null,
    contactName: newLead.value.contactName, phone: newLead.value.phone,
    company: newLead.value.company, region: newLead.value.region,
    source: newLead.value.source, owner: newLead.value.owner, next: newLead.value.next || null,
    date: new Date().toISOString().slice(0, 10), status: 'Новый лид',
  };
  db.data.leads.unshift(leadRec);
  db.save('Создан лид', leadRec.name);
  const j = db.createJourneyFromLead(leadRec.id);
  newLeadOpen.value = false;
  newLead.value = { name: '', contactName: '', phone: '', company: '', region: '', source: 'WhatsApp', owner: 'Менеджер А', next: '' };
  if (j) pick(j.id);
}

const qual = ref(null);
function openQual() {
  const q = journey.value?.qualification || {};
  qual.value = {
    clientType: q.clientType || 'Агропроизводитель', farmAction: q.farmId ? 'link' : 'none',
    farmId: journey.value?.farmId || '', newFarmName: q.newFarmName || '', region: q.region || '',
    crop: q.crop || '', area: q.area || '', need: q.need || '', contactName: q.contactName || '',
    phone: q.phone || lead.value?.phone || '', telegram: q.telegram || '', email: q.email || '',
    source: q.source || lead.value?.source || '', note: q.note || '',
  };
}
async function saveQual() { await db.saveQualification(journey.value.id, { ...qual.value }); qual.value = null; }

const dealForm = ref(null);
const saveDeal = async () => { await db.createDealFromJourney(journey.value.id, dealForm.value); dealForm.value = null; };

const pilotForm = ref(null);
const savePilot = async () => { await db.createPilotFromJourney(journey.value.id, pilotForm.value); pilotForm.value = null; };

const quoteForm = ref(null);
function openQuote() {
  quoteForm.value = { date: new Date().toISOString().slice(0, 10), terms: 'Условия: отгрузка со склада г. Бишкек, цена за упаковку.', items: [{ sku: '', packs: 1, price: 0 }] };
}
const addQItem = () => quoteForm.value.items.push({ sku: '', packs: 1, price: 0 });
const removeQItem = (i) => quoteForm.value.items.splice(i, 1);
const qLineSum = (it) => (Number(it.packs) || 0) * (Number(it.price) || 0);
const qTotal = computed(() => quoteForm.value ? quoteForm.value.items.reduce((s, it) => s + qLineSum(it), 0) : 0);
const saveQuote = async () => { await db.createQuoteFromJourney(journey.value.id, quoteForm.value); quoteForm.value = null; };

const confirmOrder = async () => { await db.confirmOrderFromQuote(journey.value.id); };
const payInvoice = async () => { await db.markInvoicePaid(invoice.value.id); };
const shipForm = ref(null);
const openShip = () => { shipForm.value = { planDate: '', carrier: '', vehicle: '', driver: '' }; };
const saveShip = async () => { await db.createShipmentFromJourney(journey.value.id, shipForm.value); shipForm.value = null; };
const recForm = ref(null);
const openRec = () => { recForm.value = { nextTask: 'Контрольный звонок после применения', nextDate: '' }; };
const saveRec = async () => { await db.confirmShipmentReceived(shipment.value.id, recForm.value); recForm.value = null; };

const nextForm = ref(null);
const openNext = () => { nextForm.value = { result: '', owner: journey.value?.owner || '', due: journey.value?.next || '' }; };
const saveNext = async () => { await db.setJourneyNext(journey.value.id, nextForm.value); nextForm.value = null; };
const setStage = async (e) => { await db.setJourneyStage(journey.value.id, e.target.value); };

function fmtTs(iso) { return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }); }
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Сквозной процесс</h1>
        <div class="subtitle">Лид → квалификация → сделка → пилот (если нужен) → КП → заказ → счёт → оплата → доставка</div>
      <BackendBadge collection="journeys" />
      </div>
      <button class="btn primary slim" @click="newLeadOpen = !newLeadOpen">＋ Создать лид</button>
    </div>

    <div v-if="newLeadOpen" class="muted-block" style="margin-bottom:14px">
      <b class="mini">ШАГ 1 · НОВОЕ ВХОДЯЩЕЕ ОБРАЩЕНИЕ</b>
      <div class="field"><label>Тема обращения *</label><input v-model="newLead.name" class="input" placeholder="Напр.: Магазин удобрений — запрос оптового прайса" /></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <div class="field" style="flex:1;min-width:140px"><label>Имя контакта</label><input v-model="newLead.contactName" class="input" /></div>
        <div class="field" style="flex:1;min-width:140px"><label>Телефон / WhatsApp</label><input v-model="newLead.phone" class="input" /></div>
        <div class="field" style="flex:1;min-width:140px"><label>Компания</label><input v-model="newLead.company" class="input" /></div>
        <div class="field" style="flex:1;min-width:140px"><label>Регион</label><input v-model="newLead.region" class="input" /></div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <div class="field" style="flex:1"><label>Источник</label>
          <select v-model="newLead.source" class="select"><option v-for="s in SOURCES" :key="s">{{ s }}</option></select>
        </div>
        <div class="field" style="flex:1"><label>Ответственный</label><input v-model="newLead.owner" class="input" /></div>
        <div class="field" style="flex:1"><label>Следующий контакт</label><input v-model="newLead.next" type="date" class="input" /></div>
      </div>
      <div class="mini" style="margin-bottom:8px">Хозяйство можно оставить неизвестным — определим при квалификации.</div>
      <button class="btn primary slim" :disabled="!newLead.name.trim()" @click="createLead">Сохранить лид и открыть маршрут</button>
    </div>

    <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
      <div style="width:280px;flex-shrink:0">
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th>Маршруты</th><th>Стадия</th></tr></thead>
            <tbody>
              <tr v-for="j in journeys" :key="j.id" class="clickrow" :class="{ selected: j.id === selectedId }" @click="pick(j.id)">
                <td>
                  <span class="txt-link">{{ db.data.leads.find(l => l.id === j.leadId)?.name || j.id }}</span>
                  <div class="mini">{{ j.id }} · {{ j.owner }}</div>
                </td>
                <td><StatusPill :status="j.stage" /></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="!journeys.length" class="empty">Нет активных маршрутов. Создайте лид — маршрут появится автоматически.</div>
      </div>

      <div v-if="journey" style="flex:1;min-width:320px">
        <div class="client-hero">
          <div>
            <div class="mini">СКВОЗНОЙ ПРОЦЕСС · {{ journey.id }} · лид {{ journey.leadId }}</div>
            <h3>{{ lead?.name || 'Лид' }}</h3>
            <div class="mini">{{ farm ? farm.name : 'Хозяйство не определено' }} · ответственный {{ journey.owner }} · след. шаг {{ day(journey.next) }}</div>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <select class="select" :value="journey.stage" @change="setStage"><option v-for="s in STAGES" :key="s">{{ s }}</option></select>
            <button class="btn ghost slim" @click="ui.go('crm')">К списку</button>
          </div>
        </div>

        <div style="display:flex;gap:4px;flex-wrap:wrap;margin:12px 0">
          <span v-for="(s, i) in STAGES.slice(0, 8)" :key="s" class="pill" :class="i <= stageIdx ? '' : 'gray'" style="font-size:11px">{{ s }}</span>
        </div>

        <!-- Шаг 3: квалификация -->
        <div class="insight"><div style="width:100%">
          <b>Шаг 3 · Квалификация контрагента</b>
          <div v-if="journey.qualification" class="mini">
            Тип: {{ journey.qualification.clientType }}<template v-if="isAgro"> · культура: {{ journey.qualification.crop || '—' }} · площадь: {{ journey.qualification.area || '—' }} га · потребность: {{ journey.qualification.need || '—' }}</template>
            · хозяйство: {{ farm ? farm.name + ' (' + farm.id + ')' : 'не привязано' }}
          </div>
          <button class="btn slim ghost" style="margin-top:6px" @click="openQual">{{ journey.qualification ? 'Изменить квалификацию' : 'Начать квалификацию' }}</button>
        </div></div>
        <div v-if="qual" class="muted-block">
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <div class="field" style="flex:1;min-width:180px"><label>Тип клиента *</label>
              <select v-model="qual.clientType" class="select"><option v-for="t in CLIENT_TYPES" :key="t">{{ t }}</option></select>
            </div>
            <div class="field" style="flex:1;min-width:180px"><label>Хозяйство</label>
              <select v-model="qual.farmAction" class="select">
                <option value="none">Не известно / создадим сейчас</option>
                <option value="link">Привязать существующее (без дублей)</option>
                <option value="create">Создать новое хозяйство</option>
              </select>
            </div>
          </div>
          <div v-if="qual.farmAction === 'link'" class="field"><label>Существующее хозяйство</label>
            <select v-model="qual.farmId" class="select">
              <option value="">— выберите —</option>
              <option v-for="f in db.farms" :key="f.id" :value="f.id">{{ f.name }} ({{ f.region }})</option>
            </select>
          </div>
          <div v-if="qual.farmAction === 'create'" class="field"><label>Название нового хозяйства *</label><input v-model="qual.newFarmName" class="input" placeholder="Проверьте написание и контакты — избегайте дублей" /></div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <div class="field" style="flex:1"><label>Регион</label><input v-model="qual.region" class="input" /></div>
            <div class="field" style="flex:1"><label>Контактное лицо</label><input v-model="qual.contactName" class="input" /></div>
            <div class="field" style="flex:1"><label>Телефон / WhatsApp</label><input v-model="qual.phone" class="input" /></div>
          </div>
          <div v-if="qual.clientType === 'Агропроизводитель'" style="display:flex;gap:8px;flex-wrap:wrap">
            <div class="field" style="flex:1"><label>Культура</label><input v-model="qual.crop" class="input" /></div>
            <div class="field" style="flex:1"><label>Площадь, га</label><input v-model="qual.area" class="input" /></div>
            <div class="field" style="flex:1"><label>Потребность</label><input v-model="qual.need" class="input" placeholder="напр. 200 л пасты" /></div>
          </div>
          <div v-else class="mini" style="margin-bottom:8px">Для магазина / оптовой базы / дилера агрономические поля необязательны, пилот не требуется.</div>
          <div style="display:flex;gap:8px">
            <button class="btn primary slim" @click="saveQual">Сохранить квалификацию</button>
            <button class="btn ghost slim" @click="qual = null">Отмена</button>
          </div>
        </div>

        <!-- Шаг 4: сделка -->
        <div class="insight"><div style="width:100%">
          <b>Шаг 4 · Сделка</b>
          <div v-if="deal" class="mini">{{ deal.title }} · {{ num(deal.volumeL) }} л · {{ money(deal.amount) }} · стадия «{{ deal.stage }}»</div>
          <div v-else class="mini">Ожидаемый объем в литрах и потенциальная сумма в сомах.</div>
          <div style="display:flex;gap:8px;margin-top:6px">
            <button v-if="!deal" class="btn slim ghost" :disabled="!journey.qualification" @click="dealForm = { volumeL: '', amount: '' }">Создать сделку</button>
            <button v-else class="btn slim ghost" @click="ui.openRecord('deal', deal.id)">Открыть сделку</button>
            <button v-if="deal" class="btn slim ghost" @click="ui.go('pipeline')">В воронке →</button>
          </div>
        </div></div>
        <div v-if="dealForm" class="muted-block">
          <div style="display:flex;gap:8px">
            <div class="field" style="flex:1"><label>Объем, л</label><input v-model="dealForm.volumeL" type="number" class="input" /></div>
            <div class="field" style="flex:1"><label>Сумма, сом</label><input v-model="dealForm.amount" type="number" class="input" /></div>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn primary slim" @click="saveDeal">Сохранить сделку</button>
            <button class="btn ghost slim" @click="dealForm = null">Отмена</button>
          </div>
        </div>

        <!-- Шаг 5: пилот (только агропроизводитель) -->
        <div v-if="isAgro" class="insight"><div style="width:100%">
          <b>Шаг 5 · Пилот (если действительно нужен)</b>
          <div v-if="pilot" class="mini">{{ pilot.id }} · {{ pilot.crop }} · {{ num(pilot.area) }} га · «{{ pilot.status }}» · контроль: {{ pilot.control || '—' }}</div>
          <div v-else class="mini">Площадь, контрольный участок, цель эксперимента. Обработки и результаты — в разделе «Агрономия».</div>
          <div style="display:flex;gap:8px;margin-top:6px">
            <button v-if="!pilot" class="btn slim ghost" :disabled="!deal" @click="pilotForm = { crop: journey.qualification?.crop || '', area: '', control: '', goal: '', date: '' }">Создать пилот</button>
            <button v-else class="btn slim ghost" @click="ui.openRecord('pilot', pilot.id)">Открыть пилот</button>
            <button v-if="pilot" class="btn slim ghost" @click="ui.go('pilots')">В агрономию →</button>
          </div>
        </div></div>
        <div v-if="pilotForm" class="muted-block">
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <div class="field" style="flex:1"><label>Культура</label><input v-model="pilotForm.crop" class="input" /></div>
            <div class="field" style="flex:1"><label>Площадь, га</label><input v-model="pilotForm.area" type="number" class="input" /></div>
            <div class="field" style="flex:1"><label>Дата старта</label><input v-model="pilotForm.date" type="date" class="input" /></div>
          </div>
          <div class="field"><label>Контрольный участок</label><input v-model="pilotForm.control" class="input" /></div>
          <div class="field"><label>Цель пилота</label><input v-model="pilotForm.goal" class="input" placeholder="напр. +15% к урожайности картофеля" /></div>
          <div style="display:flex;gap:8px">
            <button class="btn primary slim" @click="savePilot">Создать пилот</button>
            <button class="btn ghost slim" @click="pilotForm = null">Отмена</button>
          </div>
        </div>

        <!-- Шаг 6: КП → заказ → счёт → оплата → отгрузка -->
        <div class="insight"><div style="width:100%">
          <b>Шаг 6 · КП → заказ → счёт → оплата → отгрузка</b>
          <div v-if="quote" class="mini">{{ quote.number }} от {{ day(quote.date) }} · {{ quote.items.length }} поз. · {{ money(quote.total) }} · «{{ quote.status }}»</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
            <button v-if="!quote" class="btn slim ghost" :disabled="!deal" @click="openQuote">Создать КП</button>
            <button v-if="quote && !order" class="btn slim ghost" @click="confirmOrder">Подтвердить заказ (перенос из КП)</button>
            <button v-if="order && !invoice?.paid" class="btn slim ghost" @click="payInvoice">Подтвердить оплату вручную</button>
            <button v-if="invoice?.paid && !shipment" class="btn slim ghost" @click="openShip">Создать отгрузку</button>
            <button v-if="shipment && !shipment.received" class="btn slim ghost" @click="openRec">Подтвердить получение</button>
            <span v-if="shipment?.received" class="pill">Доставлено · маршрут в сопровождении</span>
          </div>
          <div v-if="order" class="mini" style="margin-top:6px">Заказ {{ order.id }} ({{ order.num }}) · счёт {{ invoice?.number }} — {{ invoice?.paid ? 'оплачен ' + day(invoice.paidAt) : 'не оплачен' }}</div>
          <div v-if="shipment" class="mini">Отгрузка {{ shipment.number }} · план {{ day(shipment.planDate) }} · перевозчик {{ shipment.carrier || '—' }} · {{ shipment.received ? 'получено клиентом' : 'в пути' }}</div>
        </div></div>
        <div v-if="quoteForm" class="muted-block">
          <div class="field" style="max-width:220px"><label>Дата КП</label><input v-model="quoteForm.date" type="date" class="input" /></div>
          <div class="mini">Позиции: продукт (SKU), упаковки, цена за упаковку</div>
          <div v-for="(it, i) in quoteForm.items" :key="i" style="display:flex;gap:6px;margin-bottom:6px;align-items:end">
            <div class="field" style="flex:2"><label v-if="i === 0">SKU</label>
              <select v-model="it.sku" class="select">
                <option value="">— выберите —</option>
                <option v-for="s in db.skus" :key="s.id" :value="s.id">{{ s.name }} ({{ s.pack }} л/уп)</option>
              </select>
            </div>
            <div class="field" style="flex:1"><label v-if="i === 0">Упаковки</label><input v-model="it.packs" type="number" class="input" /></div>
            <div class="field" style="flex:1"><label v-if="i === 0">Цена/уп, сом</label><input v-model="it.price" type="number" class="input" /></div>
            <div class="field" style="flex:1"><label v-if="i === 0">Сумма</label><div class="input" style="background:#f4f6f5">{{ money(qLineSum(it)) }}</div></div>
            <button v-if="quoteForm.items.length > 1" class="btn ghost slim" @click="removeQItem(i)">✕</button>
          </div>
          <div class="field"><label>Условия</label><textarea v-model="quoteForm.terms" class="textarea" rows="2"></textarea></div>
          <div style="display:flex;gap:8px;align-items:center">
            <button class="btn ghost slim" @click="addQItem">＋ позиция</button>
            <b style="margin-left:auto">Итого: {{ money(qTotal) }}</b>
            <button class="btn primary slim" :disabled="qTotal <= 0" @click="saveQuote">Сохранить КП</button>
            <button class="btn ghost slim" @click="quoteForm = null">Отмена</button>
          </div>
        </div>
        <div v-if="shipForm" class="muted-block">
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <div class="field" style="flex:1"><label>Плановая дата</label><input v-model="shipForm.planDate" type="date" class="input" /></div>
            <div class="field" style="flex:1"><label>Перевозчик</label><input v-model="shipForm.carrier" class="input" /></div>
            <div class="field" style="flex:1"><label>Транспорт</label><input v-model="shipForm.vehicle" class="input" placeholder="марка, гос. номер" /></div>
            <div class="field" style="flex:1"><label>Водитель</label><input v-model="shipForm.driver" class="input" /></div>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn primary slim" @click="saveShip">Создать отгрузку</button>
            <button class="btn ghost slim" @click="shipForm = null">Отмена</button>
          </div>
        </div>
        <div v-if="recForm" class="muted-block">
          <div class="field"><label>Следующая задача после доставки</label><input v-model="recForm.nextTask" class="input" /></div>
          <div class="field"><label>Дата повторного контакта</label><input v-model="recForm.nextDate" type="date" class="input" /></div>
          <div style="display:flex;gap:8px">
            <button class="btn primary slim" @click="saveRec">Подтвердить получение</button>
            <button class="btn ghost slim" @click="recForm = null">Отмена</button>
          </div>
        </div>

        <!-- Следующее действие и история -->
        <div class="insight"><div style="width:100%">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
            <b>Следующее действие</b>
            <button class="btn slim ghost" @click="openNext">Задать следующее действие</button>
          </div>
          <div class="mini">Результат, исполнитель и срок — появится связанная задача.</div>
        </div></div>
        <div v-if="nextForm" class="muted-block">
          <div class="field"><label>Результат *</label><input v-model="nextForm.result" class="input" /></div>
          <div style="display:flex;gap:8px">
            <div class="field" style="flex:1"><label>Исполнитель</label><input v-model="nextForm.owner" class="input" /></div>
            <div class="field" style="flex:1"><label>Срок</label><input v-model="nextForm.due" type="date" class="input" /></div>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn primary slim" :disabled="!nextForm.result.trim()" @click="saveNext">Сохранить</button>
            <button class="btn ghost slim" @click="nextForm = null">Отмена</button>
          </div>
        </div>

        <div style="margin-top:14px">
          <b class="mini">ИСТОРИЯ МАРШРУТА</b>
          <div v-for="(h, i) in journey.history" :key="i" class="insight" style="padding:8px 12px">
            <div><div>{{ h.text }}</div><div class="mini">{{ fmtTs(h.ts) }}</div></div>
          </div>
        </div>
      </div>

      <div v-else class="empty" style="flex:1">Выберите маршрут слева или создайте новый лид — рабочий сценарий проведёт по всем шагам.</div>
    </div>
  </div>
</template>
