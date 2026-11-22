<script setup>
// Редактор документа логистики (поставка / выгрузка) в модалке AppModal.
// Таблица позиций редактируется прямо в ячейках — как в Excel:
//   товар | кол-во | ед. | цена | сумма (авто) | примечание.
// Кнопки: добавить/удалить строку, сохранить, создать акт (печать + сохранение в документе),
// скачать .xls / .csv всего реестра — в ShipmentsView.
import { computed, reactive, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { crmFieldLabel, LOGISTICS_KINDS } from '@/data/crmFields';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import { toCsv, toXmlSpreadsheet, downloadBlob, printHtml, escapeHtml } from '@/utils/spreadsheet';

const props = defineProps({
  doc: { type: Object, default: null },   // существующий документ или null (создание)
  kind: { type: String, default: 'supply' },
  initialValues: { type: Object, default: () => ({}) },
});

const db = useDbStore();
const ui = useUiStore();
const { money, num } = useFormatters();

const label = (key) => crmFieldLabel('logistics', key);
const savedDoc = ref(props.doc?.id && !String(props.doc.id).startsWith('NEW') ? props.doc : null);
const isNew = computed(() => !savedDoc.value);
const clientId = db.uid('LOC');
const saveError = ref('');
const saving = ref(false);
const today = new Date().toISOString().slice(0, 10);

const source = props.doc || props.initialValues;
const form = reactive({
  kind: source?.kind || props.kind,
  number: source?.number || genNumber(source?.kind || props.kind),
  date: source?.date || today,
  status: source?.status || 'Черновик',
  party: source?.party || '',
  farmId: source?.farmId || '',
  orderId: source?.orderId || '',
  warehouse: source?.warehouse || '',
  vehicle: source?.vehicle || '',
  driver: source?.driver || '',
  base: source?.base || '',
  note: source?.note || '',
  items: source?.items?.length
    ? source.items.map((it) => ({ ...it }))
    : [emptyItem()],
});

function emptyItem() {
  return { skuId: '', name: '', qty: 1, unit: 'л', price: 0, note: '' };
}

function genNumber(kind) {
  return (kind === 'supply' ? 'П-' : 'В-') + clientId.slice(-8).toUpperCase();
}

const STATUSES = ['Черновик', 'Создан', 'На проверке', 'Принят', 'Отгружено', 'Доставлено', 'Оплачен', 'Закрыт', 'Отменён'];
const UNITS = ['л', 'кг', 'шт', 'упак', 'т', 'м²'];

const isDispatch = computed(() => form.kind === 'dispatch');

const lineSum = (it) => (Number(it.qty) || 0) * (Number(it.price) || 0);
const totalQty = computed(() => form.items.reduce((s, it) => s + (Number(it.qty) || 0), 0));
const totalPrice = computed(() => form.items.reduce((s, it) => s + lineSum(it), 0));

const addRow = () => form.items.push(emptyItem());
const removeRow = (i) => {
  if (form.items.length > 1) form.items.splice(i, 1);
};

// выбор SKU из каталога — подтягиваем название и цену
function onSku(i, ev) {
  const el = ev.target;
  const opt = el.selectedOptions[0];
  const it = form.items[i];
  it.skuId = el.value;
  it.name = opt?.dataset?.name || '';
  if (!it.price && opt?.dataset?.price) it.price = Number(opt.dataset.price) || 0;
}

const docPayload = () => ({
  kind: form.kind,
  number: form.number.trim(),
  date: form.date,
  status: form.status,
  party: form.party.trim(),
  farmId: form.farmId || null,
  orderId: form.orderId || null,
  warehouse: form.warehouse.trim(),
  vehicle: form.vehicle.trim(),
  driver: form.driver.trim(),
  base: form.base.trim(),
  note: form.note.trim(),
  act: savedDoc.value?.act || null,
  items: form.items.map((it) => ({
    skuId: it.skuId, name: it.name.trim(),
    qty: Number(it.qty) || 0, unit: it.unit,
    price: Number(it.price) || 0, note: (it.note || '').trim(),
    material: it.material || '', lot: (it.lot || '').trim(), qcStatus: it.qcStatus || '',
  })),
});

function validatePayload(payload) {
  payload.items = payload.items.filter((item) => item.name || item.skuId || item.material);
  if (!payload.number) throw new Error('Укажите номер документа.');
  if (!payload.items.length) throw new Error('Добавьте хотя бы одну позицию.');
  for (const item of payload.items) {
    if (!Number.isFinite(item.qty) || item.qty <= 0 || !Number.isFinite(item.price) || item.price < 0) {
      throw new Error('Укажите положительное количество и неотрицательную цену каждой позиции.');
    }
    if (item.material !== 'paste') continue;
    if (payload.kind !== 'supply' || !item.lot || !['кг', 'т'].includes(item.unit)) {
      throw new Error('Для пасты укажите партию поставщика и массу в кг или т.');
    }
    if (payload.status === 'Принят' && item.qcStatus !== 'Пройден') {
      throw new Error('Перед приёмкой подтвердите контроль качества каждой партии пасты.');
    }
  }
}

async function persist(payload) {
  validatePayload(payload);
  const document = isNew.value
    ? await db.addLogistics({ ...payload, clientId })
    : await db.updateLogistics(savedDoc.value.id, payload);
  savedDoc.value = document;
  return document;
}

async function save(closeAfter = true) {
  if (saving.value) return;
  saving.value = true;
  saveError.value = '';
  try {
    const document = await persist(docPayload());
    if (String(document.id).startsWith('LOC-')) {
      saveError.value = 'Документ пока сохранён только на этом устройстве. Откройте реестр после восстановления связи.';
    } else if (closeAfter) ui.closeModal();
  } catch (error) {
    saveError.value = error.message;
  } finally {
    saving.value = false;
  }
}

function addPasteRow() {
  const material = { ...emptyItem(), name: 'Паста-концентрат', material: 'paste', lot: '', unit: 'кг', qcStatus: 'Ожидается' };
  const first = form.items[0];
  if (form.items.length === 1 && !first.skuId && !first.name) form.items.splice(0, 1, material);
  else form.items.push(material);
}

// ── Акт приёма-передачи под документ ────────────────────────────────
const ACT_TYPES = ['Акт приёма-передачи', 'Товарная накладная (ТОРГ-12)', 'Акт выполненных работ', 'УПД'];
const actType = ref(ACT_TYPES[0]);

function actRows() {
  const rows = [['№', 'Наименование', 'Кол-во', 'Ед.', 'Цена, сом', 'Сумма, сом']];
  form.items.forEach((it, i) => {
    if (!it.name && !it.skuId) return;
    const description = it.material === 'paste' && it.lot ? `${it.name || 'Паста-концентрат'} · партия ${it.lot}` : it.name || it.skuId;
    rows.push([i + 1, description, Number(it.qty) || 0, it.unit, Number(it.price) || 0, Math.round(lineSum(it))]);
  });
  rows.push(['', '', '', '', 'ИТОГО:', Math.round(totalPrice.value)]);
  return rows;
}

function buildActHtml(actMeta) {
  const label = isDispatch.value ? 'Грузополучатель' : 'Получатель (Покупатель)';
  const supplier = isDispatch.value ? 'Грузоотправитель' : 'Поставщик';
  const rows = actRows().map((r, idx) => idx === 0
    ? `<tr>${r.map((c, j) => `<th class="${j >= 2 ? 'num' : ''}">${escapeHtml(c)}</th>`).join('')}</tr>`
    : `<tr>${r.map((c, j) => `<td class="${j >= 2 ? 'num' : ''}">${typeof c === 'number' ? num(c) : escapeHtml(c)}</td>`).join('')}</tr>`
  ).join('');
  return `
  <div class="org">ОсОО «Агро Трейд Плюс» · BIOTORF KG · ИНН _______ · тел. _______</div>
  <h1>${escapeHtml(actMeta.type)} № ${escapeHtml(actMeta.number)} от ${new Date(actMeta.date + 'T12:00:00').toLocaleDateString('ru-RU')}</h1>
  <div class="small">к документу ${isDispatch.value ? 'выгрузки (отгрузки)' : 'поставки'} № ${escapeHtml(form.number)} от ${new Date(form.date + 'T12:00:00').toLocaleDateString('ru-RU')}</div>
  <div class="grid">
    <div><b>${supplier}</b>${isDispatch.value ? 'ОсОО «Агро Трейд Плюс», склад: ' + escapeHtml(form.warehouse || '—') : escapeHtml(form.party || '—')}</div>
    <div><b>${label}</b>${isDispatch.value ? escapeHtml(form.party || '—') : escapeHtml(form.warehouse || 'Склад')} ${form.farmId ? '· ' + escapeHtml(db.farmById(form.farmId)?.name || form.farmId) : ''}</div>
    ${form.vehicle ? `<div><b>Транспорт</b>${escapeHtml(form.vehicle)}</div>` : ''}
    ${form.driver ? `<div><b>Водитель/экспедитор</b>${escapeHtml(form.driver)}</div>` : ''}
    ${form.base ? `<div><b>Основание</b>${escapeHtml(form.base)}</div>` : ''}
  </div>
  <p>Мы, нижеподписавшиеся, составили настоящий акт о том, что по указанному документу произведена
  ${isDispatch.value ? 'выгрузка (отгрузка)' : 'приёмка'} товарно-материальных ценностей в следующем количестве:</p>
  <table><thead>${rows.split('</tr>')[0]}</tr></thead><tbody>${rows.split('</tr>').slice(1).join('</tr>')}</tbody></table>
  ${form.note ? `<p class="small"><b>Примечание:</b> ${escapeHtml(form.note)}</p>` : ''}
  <p class="small">Товар передан в соответствии с документом. Замечаний по количеству, качеству и комплектности: ☐ нет ☐ имеются (см. примечания).</p>
  <div class="sign">
    <div><b>Передал:</b><div class="line"></div>${isDispatch.value ? 'Кладовщик ____________ / ' + escapeHtml(form.driver || '____________') : 'Представитель поставщика ____________'}</div>
    <div><b>Принял:</b><div class="line"></div>${isDispatch.value ? 'Представитель получателя ____________' : 'Материально ответственное лицо ____________'}</div>
  </div>`;
}

async function createAct() {
  if (saving.value) return;
  saving.value = true;
  saveError.value = '';
  try {
    const meta = {
      type: actType.value,
      number: savedDoc.value?.act?.number || ('А-' + form.number),
      date: savedDoc.value?.act?.date || form.date,
    };
    const document = await persist({ ...docPayload(), act: meta });
    printHtml(meta.type + ' ' + meta.number, buildActHtml(meta));
    if (String(document.id).startsWith('LOC-')) {
      saveError.value = 'Акт сохранён только на этом устройстве, пока нет связи с сервером.';
    } else ui.closeModal();
  } catch (error) {
    saveError.value = error.message;
  } finally {
    saving.value = false;
  }
}

function exportXls() {
  downloadBlob(toXmlSpreadsheet(actRows(), form.number), `${form.number}.xls`,
    'application/vnd.ms-excel');
}
function exportCsv() {
  downloadBlob(toCsv(actRows()), `${form.number}.csv`, 'text/csv;charset=utf-8');
}
</script>

<template>
  <div>
    <div class="formgrid" style="margin-bottom:16px">
      <div class="field">
        <label>{{ label('kind') }}</label>
        <select v-model="form.kind" class="select" :disabled="!isNew">
          <option v-for="(name, kind) in LOGISTICS_KINDS" :key="kind" :value="kind">{{ name }}</option>
        </select>
      </div>
      <div class="field"><label>{{ label('number') }}</label><input v-model="form.number" class="input" placeholder="П-001"></div>
      <div class="field"><label>{{ label('date') }}</label><input v-model="form.date" type="date" class="input"></div>
      <div class="field">
        <label>{{ label('status') }}</label>
        <select v-model="form.status" class="select">
          <option v-for="s in STATUSES" :key="s">{{ s }}</option>
        </select>
      </div>
      <div class="field">
        <label>{{ label('party') }}</label>
        <input v-model="form.party" class="input" :placeholder="isDispatch ? 'Хозяйство или контрагент' : 'Компания-поставщик'">
      </div>
      <div class="field" v-if="isDispatch">
        <label>{{ label('farmId') }}</label>
        <select v-model="form.farmId" class="select">
          <option value="">— не выбрано —</option>
          <option v-for="f in db.farms" :key="f.id" :value="f.id">{{ f.name }}</option>
        </select>
      </div>
      <div class="field">
        <label>{{ label('warehouse') }}</label>
        <input v-model="form.warehouse" class="input" placeholder="Склад Бишкек">
      </div>
      <div class="field">
        <label>{{ label('base') }}</label>
        <input v-model="form.base" class="input" placeholder="Договор №…">
      </div>
      <template v-if="isDispatch">
        <div class="field"><label>{{ label('vehicle') }}</label><input v-model="form.vehicle" class="input" placeholder="MB Sprinter · 01 AA 123 KG"></div>
        <div class="field"><label>{{ label('driver') }}</label><input v-model="form.driver" class="input"></div>
      </template>
      <div class="field full">
        <label>{{ label('note') }}</label>
        <textarea v-model="form.note" class="textarea" rows="2"></textarea>
      </div>
    </div>

    <h3 style="margin-bottom:8px">{{ label('items') }}</h3>
    <div class="table-wrap" style="margin-bottom:10px">
      <table class="table items-table">
        <thead>
          <tr>
            <th style="width:26%">{{ label('skuId') }}</th>
            <th style="width:10%" class="right-h">{{ label('qty') }}</th>
            <th style="width:9%">{{ label('unit') }}</th>
            <th style="width:13%" class="right-h">{{ label('price') }}</th>
            <th style="width:14%" class="right-h">{{ label('amount') }}</th>
            <th>{{ label('note') }}</th>
            <th style="width:34px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(it, i) in form.items" :key="i">
            <td>
              <select v-if="it.material !== 'paste'" class="input slim-in" :value="it.skuId" @change="onSku(i, $event)">
                <option value="">— свободная позиция —</option>
                <option v-for="s in db.skus" :key="s.id" :value="s.id"
                        :data-name="s.name" :data-price="s.price || 0">{{ s.name }} ({{ s.pack }})</option>
              </select>
              <input v-model="it.name" class="input slim-in" style="margin-top:4px" placeholder="Наименование">
              <template v-if="it.material === 'paste'">
                <label>{{ label('lot') }} <input v-model.trim="it.lot" class="input slim-in" maxlength="200" /></label>
                <label>{{ label('qcStatus') }}
                  <select v-model="it.qcStatus" class="input slim-in">
                    <option>Ожидается</option><option>Пройден</option><option>Отклонён</option>
                  </select>
                </label>
              </template>
            </td>
            <td><input v-model.number="it.qty" type="number" min="0" step="0.5" class="input slim-in num-in"></td>
            <td>
              <select v-model="it.unit" class="input slim-in">
                <option v-if="it.unit && !UNITS.includes(it.unit)" :value="it.unit">{{ it.unit }}</option>
                <option v-for="u in it.material === 'paste' ? ['кг', 'т'] : UNITS" :key="u">{{ u }}</option>
              </select>
            </td>
            <td><input v-model.number="it.price" type="number" min="0" step="1" class="input slim-in num-in"></td>
            <td class="mono right"><b>{{ money(lineSum(it)) }}</b></td>
            <td><input v-model="it.note" class="input slim-in" placeholder="партия, срок…"></td>
            <td><button class="btn ghost slim danger-text" title="Удалить строку" @click="removeRow(i)">✕</button></td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td colspan="2" class="text-muted">Итого позиций: {{ form.items.length }}</td>
            <td colspan="2" class="mono right text-muted">{{ num(totalQty) }}</td>
            <td class="mono right">{{ money(totalPrice) }}</td>
            <td colspan="2"></td>
          </tr>
        </tfoot>
      </table>
    </div>

    <div class="actionbar" style="margin-bottom:14px">
      <button class="btn slim" @click="addRow">＋ Строка</button>
      <button v-if="!isDispatch" class="btn slim" @click="addPasteRow">＋ Партия пасты</button>
      <button class="btn slim ghost" @click="exportXls">⬇ Скачать .xls</button>
      <button class="btn slim ghost" @click="exportCsv">⬇ Скачать .csv</button>
    </div>

    <div class="muted-block" style="margin-bottom:16px">
      <div class="mini" style="margin-bottom:8px">
        <b>Акт под документ:</b>
        <template v-if="savedDoc?.act">
          ранее создан — {{ savedDoc.act.type }} № {{ savedDoc.act.number }} от {{ savedDoc.act.date }}.
          Повторное создание перезапишет реквизиты акта.
        </template>
        <template v-else>создайте акт приёма-передачи — он сохранится в карточке документа и откроется на печать (PDF).</template>
      </div>
      <div class="actionbar">
        <select v-model="actType" class="select" style="max-width:280px">
          <option v-for="t in ACT_TYPES" :key="t">{{ t }}</option>
        </select>
        <button class="btn primary slim" :disabled="saving" @click="createAct">📄 Создать акт и открыть на печать</button>
      </div>
    </div>

    <div class="modal-foot" style="padding:0;border:0;display:flex;gap:10px;justify-content:flex-end">
      <button class="btn" @click="ui.closeModal()">Отмена</button>
      <span v-if="saveError" class="danger-text" role="alert">{{ saveError }}</span>
      <button class="btn" :disabled="saving" @click="save(false)">Сохранить и остаться</button>
      <button class="btn primary" :disabled="saving" @click="save(true)">💾 Сохранить документ</button>
    </div>
  </div>
</template>

<style scoped>
.right-h { text-align: right; }
.right { text-align: right; }
.items-table td { padding: 8px 10px; white-space: normal; }
.slim-in { padding: 7px 9px; font-size: 12px; }
.num-in { text-align: right; }
.mono { font-variant-numeric: tabular-nums; }
tfoot td { border-top: 2px solid #dfeae4; background: #fafcfb; }
</style>
