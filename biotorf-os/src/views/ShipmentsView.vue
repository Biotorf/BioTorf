<script setup>
// Раздел «Логистика»: реестры ПОСТАВОК (приход) и ВЫГРУЗОК (отгрузка) товара.
// Таблицы в стиле Excel: итоговые карточки, поиск, фильтр по статусу,
// редактирование позиций в модалке, экспорт всего реестра в .xls/.csv,
// печать реестра и создание актов приёма-передачи под каждый документ.
import { computed, onMounted, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';
import LogisticsDocEditor from '@/components/forms/LogisticsDocEditor.vue';
import { toCsv, toXmlSpreadsheet, downloadBlob, printHtml } from '@/utils/spreadsheet';

const db = useDbStore();
const ui = useUiStore();
const { money, num, day } = useFormatters();

const tab = ref('dispatch');                 // dispatch | supply
const syncing = ref(false);

onMounted(async () => {
  syncing.value = true;
  await db.syncLogistics().catch(() => false);
  syncing.value = false;
});

const docs = computed(() => db.logistics.filter((d) => d.kind === tab.value));

const filtered = computed(() => {
  const q = ui.search.toLowerCase();
  return docs.value.filter((d) => {
    if (ui.filter !== 'Все' && d.status !== ui.filter) return false;
    if (!q) return true;
    return [d.number, d.party, d.warehouse, d.base, d.driver, d.vehicle, d.status,
      (d.items || []).map((i) => i.name).join(' '),
      d.act ? `акт ${d.act.number} ${d.act.type}` : 'без акта',
    ].join(' ').toLowerCase().includes(q);
  });
});

const sumOf = (d) => (d.items || []).reduce((s, it) => s + (Number(it.qty) || 0) * (Number(it.price) || 0), 0);
const qtyOf = (d) => (d.items || []).reduce((s, it) => s + (Number(it.qty) || 0), 0);

const stats = computed(() => ({
  count: docs.value.length,
  total: docs.value.reduce((s, d) => s + sumOf(d), 0),
  acts: docs.value.filter((d) => d.act).length,
  open: docs.value.filter((d) => !['Закрыт', 'Отменён', 'Оплачен'].includes(d.status)).length,
}));

const statusOptions = computed(() =>
  ['Все', ...Array.from(new Set(docs.value.map((d) => d.status)))]);

const itemsSummary = (d) => {
  const names = (d.items || []).map((it) => it.name).filter(Boolean);
  if (!names.length) return '—';
  return names.length <= 2 ? names.join(', ') : `${names[0]} +${names.length - 1} поз.`;
};

function openEditor(doc = null) {
  ui.openModal(
    doc ? `Документ ${doc.kind === 'supply' ? 'поставки' : 'выгрузки'} ${doc.number}`
        : (tab.value === 'supply' ? 'Новая поставка' : 'Новая выгрузка (отгрузка)'),
    LogisticsDocEditor,
    { doc, kind: tab.value },
  );
}

async function removeDoc(d) {
  if (!confirm(`Удалить документ ${d.number} (${d.party || '—'})?`)) return;
  await db.removeLogistics(d.id);
}

// ── экспорт / печать всего реестра ──────────────────────────────────
function registryRows() {
  const head = tab.value === 'supply'
    ? ['Номер', 'Дата', 'Поставщик', 'Склад', 'Основание', 'Позиции', 'Кол-во', 'Сумма, сом', 'Статус', 'Акт']
    : ['Номер', 'Дата', 'Клиент/получатель', 'Склад', 'Транспорт', 'Водитель', 'Основание', 'Позиции', 'Кол-во', 'Сумма, сом', 'Статус', 'Акт'];
  const rows = filtered.value.map((d) => tab.value === 'supply'
    ? [d.number, d.date, d.party, d.warehouse, d.base, itemsSummary(d), qtyOf(d), Math.round(sumOf(d)), d.status, d.act ? `${d.act.type} №${d.act.number}` : 'нет']
    : [d.number, d.date, d.party, d.warehouse, d.vehicle, d.driver, d.base, itemsSummary(d), qtyOf(d), Math.round(sumOf(d)), d.status, d.act ? `${d.act.type} №${d.act.number}` : 'нет']);
  rows.push(['ИТОГО', '', '', '', '', '', '', Math.round(filtered.value.reduce((s, d) => s + sumOf(d), 0)), '', '']);
  return [head, ...rows];
}

function exportRegistry(fmt) {
  const rows = registryRows();
  const name = `${tab.value === 'supply' ? 'Postavki' : 'Vygruzki'}_${new Date().toISOString().slice(0, 10)}`;
  if (fmt === 'csv') downloadBlob(toCsv(rows), `${name}.csv`, 'text/csv;charset=utf-8');
  else downloadBlob(toXmlSpreadsheet(rows, name), `${name}.xls`, 'application/vnd.ms-excel');
}

function printRegistry() {
  const label = tab.value === 'supply' ? 'Реестр поставок' : 'Реестр выгрузок (отгрузок)';
  const rows = registryRows();
  const body = `<div class="org">ОсОО «Агро Трейд Плюс» · BIOTORF Business OS</div>
    <h1>${label}</h1><div class="small">на ${new Date().toLocaleDateString('ru-RU')} · документов: ${filtered.value.length}</div>
    <table><thead><tr>${rows[0].map((c) => `<th>${c}</th>`).join('')}</tr></thead>
    <tbody>${rows.slice(1, -1).map((r) => `<tr>${r.map((c, j) => `<td class="${typeof c === 'number' ? 'num' : ''}">${typeof c === 'number' ? num(c) : c}</td>`).join('')}</tr>`).join('')}</tbody>
    <tfoot><tr>${rows[rows.length - 1].map((c) => `<td class="${typeof c === 'number' ? 'num' : ''}">${typeof c === 'number' ? num(c) : c}</td>`).join('')}</tr></tfoot></table>`;
  printHtml(label, body);
}

// быстрый переход к документу для создания акта прямо из таблицы
function quickAct(d) {
  openEditor(d);
}

const partyLabel = computed(() => tab.value === 'supply' ? 'Поставщик' : 'Клиент / получатель');
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Логистика · поставки и выгрузки</h1>
        <div class="subtitle">Excel-подобные реестры документов движения товара с актами приёма-передачи</div>
      </div>
      <div class="actionbar">
        <button class="btn slim ghost" @click="exportRegistry('xls')" title="Скачать отфильтрованный реестр в Excel">⬇ Excel (.xls)</button>
        <button class="btn slim ghost" @click="exportRegistry('csv')" title="Скачать реестр в CSV">⬇ CSV</button>
        <button class="btn slim ghost" @click="printRegistry" title="Печать реестра / PDF">🖨 Печать</button>
        <button class="btn primary" @click="openEditor()">＋ {{ tab === 'supply' ? 'Новая поставка' : 'Новая выгрузка' }}</button>
      </div>
    </div>

    <div class="chips" style="margin-bottom:16px">
      <button class="btn slim" :class="{ primary: tab === 'dispatch' }" @click="tab = 'dispatch'; ui.filter = 'Все'">
        ➜ Выгрузки (отгрузки)
      </button>
      <button class="btn slim" :class="{ primary: tab === 'supply' }" @click="tab = 'supply'; ui.filter = 'Все'">
        ⬅ Поставки (приход)
      </button>
      <span v-if="syncing" class="mini right">синхронизация…</span>
    </div>

    <div class="stats">
      <div class="stat"><div class="label">Документов</div><div class="val">{{ stats.count }}</div><div class="foot">{{ tab === 'supply' ? 'поставок' : 'выгрузок' }} в реестре</div></div>
      <div class="stat"><div class="label">Сумма реестра</div><div class="val">{{ money(stats.total) }}</div><div class="foot">по позициям документов</div></div>
      <div class="stat"><div class="label">Актов создано</div><div class="val">{{ stats.acts }}</div><div class="foot">под документы</div></div>
      <div class="stat"><div class="label">Не закрыто</div><div class="val">{{ stats.open }}</div><div class="foot">требуют внимания</div></div>
    </div>

    <div class="toolbar">
      <input v-model="ui.search" class="input" :placeholder="`Поиск по ${tab === 'supply' ? 'поставкам' : 'выгрузкам'}: номер, клиент, товар, акт…`">
      <select v-model="ui.filter" class="select" style="max-width:220px">
        <option v-for="s in statusOptions" :key="s">{{ s }}</option>
      </select>
    </div>

    <div class="table-wrap">
      <table class="table reg-table">
        <thead>
          <tr>
            <th>Номер / дата</th>
            <th>{{ partyLabel }}</th>
            <th>Склад</th>
            <th v-if="tab === 'dispatch'">Транспорт / водитель</th>
            <th>Позиции</th>
            <th class="right-h">Кол-во</th>
            <th class="right-h">Сумма</th>
            <th>Статус</th>
            <th>Акт</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in filtered" :key="d.id" class="clickrow" @click="openEditor(d)">
            <td>
              <span class="txt-link">{{ d.number }}</span>
              <div class="mini">{{ day(d.date) }}</div>
            </td>
            <td>
              {{ d.party || '—' }}
              <div class="mini" v-if="d.farmId">{{ db.farmById(d.farmId)?.name || d.farmId }}</div>
              <div class="mini" v-else-if="d.base">{{ d.base }}</div>
            </td>
            <td>{{ d.warehouse || '—' }}</td>
            <td v-if="tab === 'dispatch'">
              {{ d.vehicle || '—' }}
              <div class="mini">{{ d.driver }}</div>
            </td>
            <td :title="(d.items || []).map(i => `${i.name} · ${i.qty} ${i.unit}`).join('\n')">
              {{ itemsSummary(d) }}
              <div class="mini">{{ (d.items || []).length }} поз.</div>
            </td>
            <td class="right mono">{{ num(qtyOf(d)) }}</td>
            <td class="right mono"><b>{{ money(sumOf(d)) }}</b></td>
            <td><StatusPill :status="d.status" /></td>
            <td>
              <span v-if="d.act" class="pill" :title="`${d.act.type} № ${d.act.number} от ${d.act.date}`">✓ {{ d.act.type.split(' ')[0] }} №{{ d.act.number }}</span>
              <button v-else class="btn slim ghost" @click.stop="quickAct(d)" title="Создать акт под документ">+ акт</button>
            </td>
            <td @click.stop>
              <div style="display:flex;gap:4px">
                <button class="btn slim ghost" title="Редактировать" @click="openEditor(d)">✎</button>
                <button class="btn slim ghost danger-text" title="Удалить" @click="removeDoc(d)">✕</button>
              </div>
            </td>
          </tr>
          <tr v-if="!filtered.length">
            <td colspan="11"><div class="empty">
              {{ docs.length ? 'Ничего не найдено по фильтру' :
                 `Реестр пуст — создайте первую ${tab === 'supply' ? 'поставку' : 'выгрузку'} кнопкой выше` }}
            </div></td>
          </tr>
        </tbody>
        <tfoot v-if="filtered.length">
          <tr>
            <td :colspan="tab === 'dispatch' ? 5 : 4"><b>Итого по {{ filtered.length }} док.</b></td>
            <td class="right mono">{{ num(filtered.reduce((s, d) => s + qtyOf(d), 0)) }}</td>
            <td class="right mono"><b>{{ money(filtered.reduce((s, d) => s + sumOf(d), 0)) }}</b></td>
            <td colspan="3"></td>
          </tr>
        </tfoot>
      </table>
    </div>

    <div class="note" style="margin-top:18px">
      Документы хранятся в общей базе (backend → SQLite), если сервис запущен — реестры видны всем сотрудникам.
      Клик по строке открывает редактор с таблицей позиций; там же создаётся <b>акт приёма-передачи</b>
      (печатная форма A4 → PDF) и скачиваются выгрузки в Excel/CSV.
    </div>
  </div>
</template>

<style scoped>
.right-h { text-align: right; }
.right { text-align: right; }
.mono { font-variant-numeric: tabular-nums; }
.reg-table td { vertical-align: top; }
tfoot td { border-top: 2px solid #dfeae4; background: #fafcfb; padding: 12px 14px; }
.chips .btn.primary { background: var(--green); color: #fff; border-color: var(--green); }
</style>
