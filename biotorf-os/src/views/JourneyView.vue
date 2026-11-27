<script setup>
import { isFinished } from '@/data/stockCatalog';
import { inventoryLink } from '@/utils/inventoryLink';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import CrmSelectField from '@/components/CrmSelectField.vue';
import { useFormatters } from '@/composables/useFormatters';
import { usePermissions } from '@/composables/usePermissions';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';

const db = useDbStore();
const ui = useUiStore();
const { day, money } = useFormatters();
const { canEdit, canEditCollection, canSeeFarm } = usePermissions();
const canWork = computed(() => canEditCollection('journeys'));
const clientOptions = computed(() => db.farms.filter(canSeeFarm).map((row) => ({ value: row.id, label: [row.name || row.id, row.region, row.phone].filter(Boolean).join(' · ') })));
const skuOptions = computed(() => db.skus.filter(isFinished).map((row) => ({ value: row.id, label: [row.name || row.id, row.pack ? `${row.pack} л` : ''].filter(Boolean).join(' · ') })));
const phases = ['Клиент', 'Сделка', 'Предложение', 'Заказ и оплата', 'Доставка', 'Сопровождение'];

const readSelection = () => new URLSearchParams(location.hash.split('?')[1]).get('id');
const selectedId = ref(readSelection() || (ui.activeWork?.kind === 'journey' && ui.activeWork.id) || null);
const editor = ref(null);
const form = ref({});
const error = ref('');
const feedback = ref('');
const journey = computed(() => selectedId.value ? db.journeyById(selectedId.value) : null);
const lead = computed(() => journey.value ? db.leadById(journey.value.leadId) : null);
const client = computed(() => journey.value?.farmId ? db.farmById(journey.value.farmId) : null);
const deal = computed(() => journey.value?.dealId ? db.dealById(journey.value.dealId) : null);
const pilot = computed(() => journey.value?.pilotId ? db.pilotById(journey.value.pilotId) : null);
const quote = computed(() => journey.value?.quoteId ? db.quoteById(journey.value.quoteId) : null);
const order = computed(() => journey.value?.orderId ? db.orderById(journey.value.orderId) : null);
const invoice = computed(() => journey.value?.invoiceId ? db.invoiceById(journey.value.invoiceId) : null);
const shipment = computed(() => journey.value?.shipmentId ? db.shipments.find((row) => row.id === journey.value.shipmentId) : null);
const plans = computed(() => order.value ? db.data.production.filter((row) => row.orderId === order.value.id) : []);
const isAgro = computed(() => journey.value?.qualification?.clientType === 'Агропроизводитель');
const isRetail = computed(() => journey.value?.qualification?.clientType === 'Частный покупатель');
const isPaid = computed(() => invoice.value?.paid || invoice.value?.status === 'Оплачен');
const finished = computed(() => journey.value?.stage === 'Завершено');

const journeys = computed(() => {
  const term = ui.search.trim().toLowerCase();
  return db.journeys.map((record) => {
    const subject = db.leadById(record.leadId);
    const company = record.farmId ? db.farmById(record.farmId) : null;
    return { id: record.id, name: subject?.name || company?.name || 'Заявка без темы', company: company?.name, stage: record.stage, owner: record.owner, next: record.next };
  }).filter((record) => !term || [record.name, record.company, record.owner].some((value) => String(value || '').toLowerCase().includes(term)))
    .sort((a, b) => Number(a.stage === 'Завершено') - Number(b.stage === 'Завершено') ||
      String(a.next || '9999').localeCompare(String(b.next || '9999')));
});

function closeEditor() {
  editor.value = null;
  form.value = {};
  error.value = '';
}

function pick(id) {
  closeEditor();
  feedback.value = '';
  selectedId.value = id;
  ui.activeWork = { kind: 'journey', id };
  const url = '#/journey?' + new URLSearchParams({ id });
  if (location.hash !== url) history.replaceState(null, '', url);
}

function syncSelection() {
  if (!/^#\/?journey(?:\?|$)/.test(location.hash)) return;
  const id = readSelection() || journeys.value[0]?.id;
  if (id && id !== selectedId.value) pick(id);
}
onMounted(() => window.addEventListener('hashchange', syncSelection));
onUnmounted(() => window.removeEventListener('hashchange', syncSelection));

watch(() => ui.activeWork?.kind === 'journey' && ui.activeWork.id, (id) => {
  if (id && id !== selectedId.value) pick(id);
});
watch(journeys, (rows) => {
  if (!selectedId.value && rows.length) pick(rows[0].id);
}, { immediate: true });

function matchingClient(phone) {
  const normalize = (value) => String(value || '').replace(/\D/g, '');
  const key = normalize(phone);
  if (key.length < 7) return null;
  const ids = new Set(db.farms.filter((row) => normalize(row.phone) === key).map((row) => row.id));
  for (const contact of db.data.contacts || []) {
    if (normalize(contact.phone) === key || normalize(contact.whatsapp) === key) ids.add(contact.farmId);
  }
  const match = ids.size === 1 ? db.farmById([...ids][0]) : null;
  return match && canSeeFarm(match) ? match : null;
}

function openEditor(key) {
  error.value = '';
  editor.value = key;
  const q = journey.value?.qualification || {};
  const selectedClient = key === 'qualification' ? client.value || matchingClient(q.phone || lead.value?.phone) : null;
  const forms = {
    lead: () => ({ name: '', contactName: '', phone: '', company: '', region: '', source: '', owner: ui.name || ui.login || '', next: '' }),
    qualification: () => ({
      clientType: q.clientType || selectedClient?.type || '', farmAction: selectedClient ? 'link' : 'create',
      farmId: selectedClient?.id || '', newFarmName: lead.value?.company || q.newFarmName || lead.value?.contactName || '',
      region: q.region || lead.value?.region || '', crop: q.crop || '', area: q.area || '', need: q.need || '',
      contactName: q.contactName || lead.value?.contactName || '', phone: q.phone || lead.value?.phone || '',
      telegram: q.telegram || '', email: q.email || '', source: q.source || lead.value?.source || '', note: q.note || '',
    }),
    deal: () => ({ volumeL: '', amount: '' }),
    pilot: () => ({ crop: q.crop || '', area: '', control: '', goal: '', date: '' }),
    quote: () => ({ date: new Date().toISOString().slice(0, 10), terms: '', items: [{ sku: '', packs: 1, price: '' }] }),
    shipment: () => ({ planDate: '', carrier: '', vehicle: '', driver: '' }),
    received: () => ({ nextTask: isAgro.value ? 'Уточнить результат применения' : 'Уточнить, всё ли в порядке с заказом', nextDate: '' }),
    followup: () => ({ result: '', owner: journey.value?.owner || '', due: journey.value?.next || '' }),
  };
  form.value = forms[key]();
}

function saveLead() {
  const values = form.value;
  if (!values.name.trim()) throw new Error('Укажите тему заявки.');
  const record = { ...values, id: db.uid('L'), name: values.name.trim(), farmId: null, next: values.next || null,
    date: new Date().toISOString().slice(0, 10), status: 'Новый лид' };
  db.data.leads.unshift(record);
  db.save('Создан лид', record.name);
  const created = db.createJourneyFromLead(record.id);
  pick(created.id);
  return created;
}

function run(action) {
  error.value = '';
  feedback.value = '';
  try {
    return action();
  } catch (e) {
    error.value = e.message || 'Не удалось сохранить изменения.';
    return null;
  }
}

function saveEditor() {
  const id = journey.value?.id;
  const value = { ...form.value };
  const save = {
    lead: saveLead,
    qualification: () => {
      if (!value.clientType) throw new Error('Выберите тип клиента.');
      if (value.farmAction === 'link' && !clientOptions.value.some(({ value: id }) => id === value.farmId)) {
        throw new Error('Выберите существующего клиента.');
      }
      if (!isAgroType(value.clientType)) Object.assign(value, { crop: '', area: '', need: '' });
      if (value.farmAction === 'create' && !value.newFarmName.trim()) {
        value.newFarmName = value.contactName?.trim() || lead.value?.name || '';
      }
      return db.saveQualification(id, value);
    },
    deal: () => db.createDealFromJourney(id, value),
    pilot: () => db.createPilotFromJourney(id, value),
    quote: () => {
      if (isRetail.value && !deal.value) {
        const valid = value.items.every((item) => {
          const sku = item.sku && db.skuById(item.sku);
          return sku && Number(sku.pack) > 0 && Number.isSafeInteger(Number(item.packs)) && Number(item.packs) > 0 &&
            Number.isFinite(Number(item.price)) && Number(item.price) > 0;
        });
        if (!valid) throw new Error('Выберите товар с указанной фасовкой и проверьте количество и цену.');
        db.createDealFromJourney(id, {
          volumeL: value.items.reduce((sum, item) => sum + Number(item.packs) * Number(db.skuById(item.sku).pack), 0),
          amount: quoteTotal.value,
        });
      }
      return db.createQuoteFromJourney(id, value);
    },
    shipment: () => db.createShipmentFromJourney(id, value),
    received: () => db.confirmShipmentReceived(shipment.value.id, value),
    followup: () => db.setJourneyNext(id, value),
  };
  if (run(save[editor.value])) closeEditor();
}
function isAgroType(type) { return type === 'Агропроизводитель'; }

function completeSale() {
  if (!shipment.value?.received) return;
  run(() => {
    db.setJourneyStage(journey.value.id, 'Завершено');
    if (deal.value && deal.value.stage !== 'Завершена') db.editEntity('deal', deal.value.id, { stage: 'Завершена' });
  });
}

async function copyQuote() {
  const offer = quote.value;
  if (!offer) return;
  const lines = (offer.items || []).map((item) => `${item.name || item.sku} — ${item.packs} уп. × ${money(item.price)}`);
  const text = [`Предложение ${offer.number || ''}`.trim(), ...lines, `Итого ${money(offer.total)}`, offer.terms].filter(Boolean).join('\n');
  try {
    await navigator.clipboard.writeText(text);
    feedback.value = 'Предложение скопировано.';
  } catch {
    error.value = 'Не удалось скопировать предложение. Его можно открыть в связанных документах.';
  }
}

function payInvoice() {
  const balance = db.invoiceBalance(invoice.value);
  const question = balance > 0
    ? `Подтвердить поступление ${money(balance)} по счёту ${invoice.value.number}?`
    : `Подтвердить сверку платежей по счёту ${invoice.value.number}?`;
  if (window.confirm(question)) run(() => db.markInvoicePaid(invoice.value.id));
}

const next = computed(() => {
  if (finished.value) return { phase: 5, title: 'Сделка завершена', text: 'Документы и история доступны в карточке.' };
  if (shipment.value?.received) return { phase: 5, title: 'Сопроводите клиента', text: 'Запланируйте следующий контакт после доставки.', button: 'Запланировать контакт', action: () => openEditor('followup') };
  if (shipment.value) return { phase: 4, title: 'Подтвердите доставку', text: 'Когда покупатель получит товар, отметьте доставку и запланируйте следующий контакт.', button: 'Подтвердить получение', action: () => openEditor('received') };
  if (isPaid.value) return { phase: 4, title: 'Организуйте доставку', text: 'Согласуйте с клиентом дату и способ передачи заказа.', button: 'Оформить отгрузку', action: () => openEditor('shipment') };
  if (invoice.value) return { phase: 3, title: 'Сверьте оплату', text: `${invoice.value.number || 'Счёт'} · К оплате ${money(db.invoiceBalance(invoice.value))}`, button: 'Подтвердить оплату', action: payInvoice };
  if (order.value) return { phase: 3, title: 'Проверьте счёт', text: 'У заказа нет связанного счёта. Откройте заказ, чтобы проверить документы.', button: 'Открыть заказ', action: () => ui.openRecord('order', order.value.id) };
  if (quote.value?.status === 'Черновик') return { phase: 2, title: 'Передайте предложение клиенту', text: 'После отправки в согласованном канале отметьте это в сделке.', button: 'Отметить отправку', action: () => run(() => db.markQuoteSent(journey.value.id)) };
  if (['Отправлено', 'Принят'].includes(quote.value?.status)) return { phase: 3, title: 'Подтвердите согласие клиента', text: 'После подтверждения появятся заказ, счёт и потребность производства по каждому артикулу.', button: 'Оформить заказ', action: () => run(() => db.confirmOrderFromQuote(journey.value.id)) };
  if (deal.value || isRetail.value) return { phase: deal.value ? 2 : 1, title: 'Подготовьте предложение',
    text: isRetail.value && !deal.value ? 'Укажите товары, упаковки и цены. Сделка создастся вместе с черновиком предложения.'
      : 'Укажите товары, упаковки и цены. Предложение сохранится черновиком.', button: 'Подготовить КП', action: () => openEditor('quote') };
  if (journey.value?.qualification) return { phase: 1, title: 'Откройте сделку', text: 'Можно указать ожидаемые объём и сумму. Точный состав заказа появится позже.', button: 'Создать сделку', action: () => openEditor('deal') };
  return { phase: 0, title: 'Уточните, кто клиент', text: 'Привяжите заявку к существующей карточке или создайте нового клиента.', button: 'Уточнить клиента', action: () => openEditor('qualification') };
});

const documents = computed(() => [
  ['deal', 'Сделка', deal.value, deal.value?.title],
  ['pilot', 'Пилот', pilot.value, pilot.value?.crop],
  ['quote', 'Предложение', quote.value, quote.value?.number],
  ['order', 'Заказ', order.value, order.value?.number || order.value?.num],
  ['invoice', 'Счёт', invoice.value, invoice.value?.number],
  ['shipment', 'Отгрузка', shipment.value, shipment.value?.number],
].filter(([, , record]) => record));
const quoteTotal = computed(() => editor.value === 'quote'
  ? form.value.items.reduce((sum, line) => sum + Number(line.packs || 0) * Number(line.price || 0), 0) : 0);
const formTitles = { lead: 'Новая заявка', qualification: 'Данные клиента', deal: 'Новая сделка', pilot: 'Новый пилот',
  quote: 'Предложение клиенту', shipment: 'Новая отгрузка', received: 'Подтверждение доставки', followup: 'Следующий контакт' };

function skuChanged(line) {
  const sku = line.sku ? db.skuById(line.sku) : null;
  if (sku?.price > 0) line.price = sku.price;
}
</script>

<template>
  <section class="sales-page">
    <header class="pagehead sales-head">
      <div>
        <h1>Сквозной процесс</h1>
        <p class="subtitle">Продажи Agro и Home от заявки до доставки.</p>
      </div>
      <div class="actionbar">
        <BackendBadge collection="journeys" />
        <button v-if="canWork" type="button" class="btn primary" data-tour="sale-create" @click="openEditor('lead')">＋ Новая заявка</button>
      </div>
    </header>

    <div class="sales-grid">
      <aside class="panel sales-inbox" data-tour="sale-list" aria-label="Заявки">
        <div class="rail-title"><h2>Заявки</h2><span class="mini">{{ journeys.length }}</span></div>
        <input v-model="ui.search" class="input" type="search" placeholder="Имя или компания" aria-label="Поиск по заявкам" />
        <div v-if="journeys.length" class="request-list">
          <button v-for="entry in journeys" :key="entry.id" type="button" class="request"
            :aria-current="entry.id === selectedId ? 'true' : undefined" @click="pick(entry.id)">
            <strong>{{ entry.name }}</strong>
            <span v-if="entry.company && entry.company !== entry.name" class="request-meta">{{ entry.company }}</span>
            <span class="request-meta">{{ entry.stage }}<template v-if="entry.next"> · {{ day(entry.next) }}</template></span>
          </button>
        </div>
        <p v-else class="mini rail-empty">{{ ui.search ? 'Заявки не найдены.' : 'Заявок пока нет.' }}</p>
      </aside>

      <div class="sales-detail">
        <section v-if="journey && editor !== 'lead'" class="panel sale-summary">
          <div class="summary-title">
            <div>
              <h2>{{ lead?.name || client?.name || 'Заявка' }}</h2>
              <p class="subtitle">
                <button v-if="client" type="button" class="link-button" @click="ui.openClient(client.id)">{{ client.name }}</button>
                <template v-else>Клиент ещё не привязан</template>
                <template v-if="journey.owner"> · {{ journey.owner }}</template>
              </p>
            </div>
            <span v-if="journey.qualification?.clientType" class="pill">{{ journey.qualification.clientType }}</span>
          </div>

          <ol class="sale-steps" aria-label="Этапы продажи">
            <li v-for="(phase, index) in phases" :key="phase" :aria-current="index === next.phase && !finished ? 'step' : undefined" :class="{ done: finished || index < next.phase }">
              <span class="step-mark" aria-hidden="true">{{ finished || index < next.phase ? '✓' : index + 1 }}</span>{{ phase }}
            </li>
          </ol>

          <section v-if="!editor" class="next-panel" data-tour="sale-next" aria-label="Следующий шаг">
            <div>
              <h3>{{ next.title }}</h3>
              <p>{{ next.text }}</p>
              <p v-if="journey.next" class="mini next-date">Следующий контакт {{ day(journey.next) }}</p>
            </div>
            <button v-if="next.button && canWork" type="button" class="btn primary" @click="next.action()">{{ next.button }}</button>
          </section>
        </section>

        <p v-if="error && !editor" class="form-error" role="alert">{{ error }}</p>
        <p v-if="feedback && !editor" class="form-feedback" role="status">{{ feedback }}</p>
        <form v-if="editor" class="panel sale-form" @submit.prevent="saveEditor">
          <h2>{{ formTitles[editor] }}</h2>
          <div v-if="editor === 'lead'" class="formgrid">
            <label class="field full">Тема заявки<input v-model.trim="form.name" class="input" required placeholder="Например, магазин запрашивает прайс BioTorf Home" /></label>
            <label class="field">Контакт<input v-model="form.contactName" class="input" autocomplete="name" /></label>
            <label class="field">Телефон<input v-model="form.phone" class="input" type="tel" /></label>
            <details class="full form-details">
              <summary>Дополнительные данные</summary>
              <div class="formgrid">
                <label class="field">Компания<input v-model="form.company" class="input" /></label>
                <CrmSelectField v-model="form.region" label="Регион" :options="db.optionsFor('regions', 'leads', 'region')" list-key="regions" />
                <CrmSelectField v-model="form.source" label="Источник" :options="db.optionsFor('sources', 'leads', 'source')" list-key="sources" />
                <CrmSelectField v-model="form.owner" label="Ответственный" :options="db.optionsFor('owners', 'leads', 'owner')" list-key="owners" />
                <label class="field">Дата следующего контакта<input v-model="form.next" class="input" type="date" /></label>
              </div>
            </details>
          </div>
          <div v-else-if="editor === 'qualification'" class="formgrid">
            <CrmSelectField v-model="form.clientType" label="Тип клиента" :options="db.optionsFor('types', 'farms', 'type')" list-key="types" required />
            <label class="field">Карточка клиента<select v-model="form.farmAction" class="select" aria-label="Карточка клиента">
              <option value="create">Создать карточку</option><option value="link">Выбрать существующую</option><option value="none">Уточнить позже</option>
            </select></label>
            <CrmSelectField v-if="form.farmAction === 'link'" v-model="form.farmId" class="full" label="Существующий клиент"
              :options="clientOptions" placeholder="Выберите клиента" searchable required />
            <label v-if="form.farmAction === 'create'" class="field full">Имя или название<input v-model="form.newFarmName" class="input" :placeholder="lead?.name || ''" /></label>
            <label class="field">Контактное лицо<input v-model="form.contactName" class="input" /></label>
            <label class="field">Телефон<input v-model="form.phone" class="input" type="tel" /></label>
            <template v-if="isAgroType(form.clientType)">
              <CrmSelectField v-model="form.crop" label="Культура" :options="db.optionsFor('crops', 'pilots', 'crop')" list-key="crops" />
              <label class="field">Площадь, га<input v-model="form.area" class="input" type="number" min="0" step="any" /></label>
              <label class="field full">Потребность<input v-model="form.need" class="input" /></label>
            </template>
            <details class="full form-details">
              <summary>Дополнительные данные</summary>
              <div class="formgrid">
                <CrmSelectField v-model="form.region" label="Регион" :options="db.optionsFor('regions', 'farms', 'region')" list-key="regions" />
                <label class="field">Telegram<input v-model="form.telegram" class="input" /></label>
                <label class="field">Почта<input v-model="form.email" class="input" type="email" /></label>
                <CrmSelectField v-model="form.source" label="Источник" :options="db.optionsFor('sources', 'farms', 'source')" list-key="sources" />
                <label class="field full">Примечание<textarea v-model="form.note" class="textarea" rows="2" /></label>
              </div>
            </details>
          </div>
          <div v-else-if="editor === 'deal'" class="formgrid">
            <label class="field">Ожидаемый объём, л<input v-model="form.volumeL" class="input" type="number" min="0" step="any" /></label>
            <label class="field">Ожидаемая сумма, сом<input v-model="form.amount" class="input" type="number" min="0" step="0.01" /></label>
          </div>
          <div v-else-if="editor === 'pilot'" class="formgrid">
            <CrmSelectField v-model="form.crop" label="Культура" :options="db.optionsFor('crops', 'pilots', 'crop')" list-key="crops" />
            <label class="field">Площадь, га<input v-model="form.area" class="input" type="number" min="0" step="any" /></label>
            <label class="field">Контрольный участок<input v-model="form.control" class="input" /></label>
            <label class="field">Дата старта<input v-model="form.date" class="input" type="date" /></label>
            <label class="field full">Цель пилота<input v-model="form.goal" class="input" /></label>
          </div>
          <div v-else-if="editor === 'quote'" class="quote-form">
            <div v-for="(line, index) in form.items" :key="index" class="quote-line">
              <CrmSelectField v-model="line.sku" label="Товар" :options="skuOptions" placeholder="Выберите товар" searchable required @change="skuChanged(line)" />
              <label class="field">Упаковки<input v-model="line.packs" class="input" type="number" min="1" required /></label>
              <label class="field">Цена упаковки, сом<input v-model="line.price" class="input" type="number" min="0.01" step="0.01" required /></label>
              <button v-if="form.items.length > 1" type="button" class="btn slim ghost" :aria-label="`Убрать позицию ${index + 1}`" @click="form.items.splice(index, 1)">Убрать</button>
            </div>
            <div class="actionbar quote-total">
              <button type="button" class="btn slim ghost" @click="form.items.push({ sku: '', packs: 1, price: '' })">＋ Товар</button>
              <strong>{{ money(quoteTotal) }}</strong>
            </div>
            <div class="formgrid">
              <label class="field">Дата предложения<input v-model="form.date" class="input" type="date" /></label>
              <label class="field full">Условия<textarea v-model="form.terms" class="textarea" rows="2" /></label>
            </div>
          </div>
          <div v-else-if="editor === 'shipment'" class="formgrid">
            <label class="field">Плановая дата<input v-model="form.planDate" class="input" type="date" /></label>
            <CrmSelectField v-model="form.carrier" label="Перевозчик" :options="db.optionsFor('carriers', 'shipments', 'carrier')" list-key="carriers" />
            <CrmSelectField v-model="form.vehicle" label="Транспорт" :options="db.optionsFor('transport', 'shipments', 'vehicle')" list-key="transport" />
            <CrmSelectField v-model="form.driver" label="Водитель" :options="db.optionsFor('drivers', 'shipments', 'driver')" list-key="drivers" />
          </div>
          <div v-else-if="editor === 'received'" class="formgrid">
            <label class="field full">Задача после доставки<input v-model="form.nextTask" class="input" /></label>
            <label class="field">Дата следующего контакта<input v-model="form.nextDate" class="input" type="date" /></label>
          </div>
          <div v-else-if="editor === 'followup'" class="formgrid">
            <label class="field full">Что нужно сделать<input v-model.trim="form.result" class="input" required /></label>
            <CrmSelectField v-model="form.owner" label="Ответственный" :options="db.optionsFor('owners', 'tasks', 'owner')" list-key="owners" />
            <label class="field">Срок<input v-model="form.due" class="input" type="date" /></label>
          </div>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <div class="actionbar form-actions">
            <button type="submit" class="btn primary">{{ editor === 'quote' ? 'Сохранить черновик' : 'Сохранить' }}</button>
            <button type="button" class="btn ghost" @click="closeEditor">Отмена</button>
          </div>
        </form>

        <section v-if="journey && !editor" class="panel supporting">
          <div v-if="canWork || quote" class="actionbar supporting-actions">
            <a v-if="order && canEdit('warehouse')" class="btn slim ghost" :href="inventoryLink('reserve', 'orders', order.id, order.id)">Резерв на складе</a>
            <a v-if="shipment && canEdit('warehouse')" class="btn slim ghost" :href="inventoryLink('dispatch', 'shipments', shipment.id, shipment.orderId)">Списать со склада</a>
            <a v-if="shipment && canEdit('shipments')" class="btn slim ghost" :href="'#/shipments?shipment=' + encodeURIComponent(shipment.id)">Документ и акт</a>
            <button v-if="quote && !order" type="button" class="btn slim ghost" @click="copyQuote">Скопировать КП</button>
            <button v-if="canWork" type="button" class="btn slim ghost" @click="openEditor('qualification')">Данные клиента</button>
            <button v-if="canWork && isAgro && deal && !pilot && !finished" type="button" class="btn slim ghost" @click="openEditor('pilot')">Добавить пилот</button>
            <button v-if="canWork && next.phase !== 5 && !finished" type="button" class="btn slim ghost" @click="openEditor('followup')">Поставить задачу</button>
            <button v-if="canWork && shipment?.received && !finished" type="button" class="btn slim ghost" @click="completeSale">Завершить сделку</button>
          </div>
          <details v-if="documents.length || plans.length" class="support-item">
            <summary>Связанные документы</summary>
            <ul>
              <li v-for="[kind, label, record, name] in documents" :key="record.id">
                <button type="button" class="link-button" @click="ui.openRecord(kind, record.id)">{{ label }}<template v-if="name"> · {{ name }}</template></button>
              </li>
              <li v-for="plan in plans" :key="plan.id"><a :href="'#/registry?table=production&id=' + encodeURIComponent(plan.id)">План производства · {{ plan.product }}</a></li>
            </ul>
          </details>
          <details v-if="journey.history?.length" class="support-item">
            <summary>История</summary>
            <ul>
              <li v-for="entry in journey.history" :key="entry.ts + entry.text">{{ entry.text }} <span class="mini">{{ day(entry.ts) }}</span></li>
            </ul>
          </details>
        </section>

        <section v-if="!journey && !editor" class="panel sales-empty">
          <h2>{{ selectedId ? 'Заявка не найдена' : 'Начните с заявки' }}</h2>
          <p class="subtitle">{{ selectedId ? 'Выберите доступную заявку в списке.' : 'Выберите обращение или создайте заявку, чтобы пройти сделку по шагам.' }}</p>
          <button v-if="!selectedId && canWork" type="button" class="btn primary" @click="openEditor('lead')">Создать заявку</button>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sales-head { margin-bottom: 16px; align-items: center; }
.sales-head p, .summary-title p { margin-bottom: 0; }
.sales-grid { display: grid; grid-template-columns: minmax(180px, 250px) minmax(0, 1fr); gap: 16px; align-items: start; }
.sales-detail { display: grid; gap: 12px; min-width: 0; }
.sales-inbox { padding: 14px; min-width: 0; }
.rail-title, .summary-title { display: flex; justify-content: space-between; align-items: start; gap: 10px; }
.rail-title { margin-bottom: 10px; align-items: center; }
.request-list { display: grid; gap: 5px; max-height: 62vh; overflow: auto; margin-top: 10px; }
.request { display: grid; gap: 3px; text-align: left; padding: 9px 10px; background: #fff; color: var(--ink);
  border: 1px solid var(--border); border-radius: 8px; overflow-wrap: anywhere; }
.request:hover, .request[aria-current] { border-color: #8fc8aa; background: #edf7f0; }
.request-meta { color: var(--muted); font-size: 12px; }
.rail-empty { margin: 12px 0 0; }
.sale-steps { list-style: none; margin: 18px 0; padding: 0; display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px; }
.sale-steps li { display: grid; justify-items: center; align-content: start; gap: 4px; text-align: center; font-size: 11px; color: #64796d; }
.step-mark { display: grid; place-items: center; height: 25px; width: 25px; border-radius: 50%; background: #edf3ef; font-weight: 700; }
.sale-steps .done .step-mark { background: #e0f1e6; color: #1f744a; }
.sale-steps [aria-current] { color: #1f744a; font-weight: 700; }
.sale-steps [aria-current] .step-mark { background: var(--green); color: #fff; }
.next-panel { padding: 15px; border: 1px solid #cce5d4; border-radius: 11px; background: #eff8f2; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.next-panel h3 { margin-bottom: 3px; }
.next-panel p { margin-bottom: 0; }
.next-panel .btn { flex-shrink: 0; }
.next-date { margin-top: 6px; }
.link-button { border: 0; background: none; color: var(--green); padding: 0; text-align: left; font-weight: 650; }
.link-button:hover { text-decoration: underline; }
.supporting { padding: 14px 20px; }
.supporting-actions { margin-bottom: 4px; }
.support-item, .form-details { padding: 8px 0; }
.support-item + .support-item { border-top: 1px solid var(--border); }
.support-item summary, .form-details summary { font-weight: 650; cursor: pointer; }
.support-item ul { margin: 8px 0 0; padding-left: 20px; display: grid; gap: 4px; }
.sale-form h2 { margin-bottom: 12px; }
.form-details .formgrid { margin-top: 8px; }
.full { grid-column: 1 / -1; }
.form-actions { margin-top: 14px; }
.quote-line { display: grid; grid-template-columns: minmax(120px, 2fr) minmax(64px, 1fr) minmax(100px, 1fr) auto; align-items: end; gap: 8px; margin-bottom: 9px; }
.quote-total { justify-content: space-between; margin-bottom: 12px; }
.form-error, .form-feedback { margin: 10px 0 0; }
.form-error { color: #a12924; }
.form-feedback { color: var(--green); }
.sales-empty { display: grid; justify-items: start; gap: 8px; }
@media (max-width: 850px) {
  .sales-grid { grid-template-columns: 1fr; }
  .request-list { max-height: 180px; }
}
@media (max-width: 580px) {
  .sale-steps { grid-template-columns: repeat(3, 1fr); row-gap: 9px; }
  .next-panel { align-items: flex-start; flex-direction: column; }
  .next-panel .btn { max-width: 100%; }
  .quote-line { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .quote-line .field:first-child { grid-column: 1 / -1; }
}
</style>
