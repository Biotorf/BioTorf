<script setup>
// «Календарь» (руководство v0.9 §2, §7): все датированные события; режимы
// День / Неделя / Месяц; листание стрелками, «Сегодня»; «События периода» списком.
import { computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';

const db = useDbStore();
const ui = useUiStore();
const { day } = useFormatters();

const MODES = ['День', 'Неделя', 'Месяц'];
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const startOfWeek = (d) => addDays(d, -((d.getDay() + 6) % 7));
const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

const anchor = computed(() => ui.calAnchor || new Date());
const mode = computed(() => ui.calMode || 'Месяц');

// ── все датированные события из реестров ────────────────────────────────
const events = computed(() => {
  const ev = [];
  for (const t of db.tasks) if (t.due) ev.push({ date: t.due, title: t.title, kind: 'task', id: t.id, meta: `Задача · ${t.owner} · ${t.status}` });
  for (const f of db.farms) if (f.next) ev.push({ date: f.next, title: `Контакт: ${f.name}`, kind: 'farm', id: f.id, meta: 'Хозяйство · следующий контакт' });
  for (const l of db.leads) if (l.next) ev.push({ date: l.next, title: `Лид: ${l.name}`, kind: 'lead', id: l.id, meta: `Лид · ${l.owner} · ${l.status}` });
  for (const j of db.journeys) if (j.next) ev.push({ date: j.next, title: `Маршрут ${j.id}: ${j.stage}`, kind: 'journey', id: j.id, meta: 'Сквозной процесс · следующее действие' });
  for (const sh of db.shipments) if (sh.plannedDate) ev.push({ date: sh.plannedDate, title: `Отгрузка ${sh.number}`, kind: 'shipment', id: sh.id, meta: `Доставка · ${sh.carrier || ''}` });
  return ev.sort((a, b) => a.date.localeCompare(b.date));
});

const byDate = computed(() => {
  const m = {};
  for (const e of events.value) (m[e.date] ??= []).push(e);
  return m;
});

// ── сетки ────────────────────────────────────────────────────────────────
const cells = computed(() => {
  const a = anchor.value;
  if (mode.value === 'День') return [new Date(a)];
  if (mode.value === 'Неделя') { const s = startOfWeek(a); return Array.from({ length: 7 }, (_, i) => addDays(s, i)); }
  const first = new Date(a.getFullYear(), a.getMonth(), 1);
  const start = startOfWeek(first);
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
});

const periodLabel = computed(() => {
  const a = anchor.value;
  if (mode.value === 'День') return day(iso(a));
  if (mode.value === 'Неделя') { const s = startOfWeek(a); return `${day(iso(s))} — ${day(iso(addDays(s, 6)))}`; }
  return a.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
});

const periodEvents = computed(() => {
  const cs = cells.value;
  const lo = iso(cs[0]), hi = iso(cs[cs.length - 1]);
  return events.value.filter((e) => e.date >= lo && e.date <= hi);
});

function shift(n) {
  const a = new Date(anchor.value);
  if (mode.value === 'День') addDays(a, n) && Object.assign(a, addDays(a, n));
  const d = mode.value === 'День' ? n : mode.value === 'Неделя' ? n * 7 : n * 30;
  ui.calAnchor = addDays(anchor.value, d);
}
function today() { ui.calAnchor = new Date(); }
function openEvent(e) {
  if (e.kind === 'journey') ui.openJourney(e.id);
  else if (e.kind === 'lead') ui.openLeadCard(e.id);
  else if (e.kind === 'farm') ui.openClient(e.id);
  else ui.openRecord(e.kind, e.id);
}
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Календарь</h1>
        <div class="subtitle">{{ periodLabel }} · всего событий: {{ events.length }}</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn slim" @click="ui.go(ui.calendarPrev || 'dashboard')">← Назад</button>
        <select class="select" v-model="ui.calMode" style="max-width:130px"><option v-for="m in MODES" :key="m">{{ m }}</option></select>
        <button class="btn slim" @click="shift(-1)">‹</button>
        <button class="btn slim" @click="today()">Сегодня</button>
        <button class="btn slim" @click="shift(1)">›</button>
      </div>
    </div>

    <section class="panel">
      <div v-if="mode !== 'День'" class="table" style="border:none">
        <div style="display:grid;grid-template-columns:repeat(7,1fr);text-align:center;font-weight:600;padding:6px 0">
          <span v-for="w in WEEKDAYS" :key="w">{{ w }}</span>
        </div>
      </div>
      <div :style="{ display:'grid', gridTemplateColumns: mode==='День' ? '1fr' : 'repeat(7,1fr)', gap:'1px', background:'#e5e7eb' }">
        <div v-for="c in cells" :key="c.toISOString()" class="cal-cell" :class="{ other: c.getMonth() !== anchor.getMonth() && mode==='Месяц', today: sameDay(c, new Date()) }">
          <div class="mini" style="font-weight:600">{{ c.getDate() }}</div>
          <div
            v-for="(e, i) in (byDate[iso(c)] || []).slice(0, 9)"
            :key="e.id + i"
            class="cal-ev"
            :title="e.meta"
            @click="openEvent(e)"
          >{{ e.title }}</div>
          <div v-if="(byDate[iso(c)] || []).length > 9" class="mini">…ещё {{ byDate[iso(c)].length - 9 }}</div>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-top:14px">
      <div class="panel-head"><div class="panel-title">События периода</div></div>
      <table class="table">
        <thead><tr><th>Дата</th><th>Событие</th><th>Тип</th></tr></thead>
        <tbody>
          <tr v-for="(e, i) in periodEvents" :key="e.id + '-' + i" class="row-click" @click="openEvent(e)">
            <td>{{ day(e.date) }}</td>
            <td><b>{{ e.title }}</b></td>
            <td class="mini">{{ e.meta }}</td>
          </tr>
          <tr v-if="!periodEvents.length"><td colspan="3" class="empty">В выбранном периоде событий нет</td></tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.cal-cell { background: #fff; min-height: 92px; padding: 6px; overflow: hidden; }
.cal-cell.other { background: #f6f7f8; color: #9ca3af; }
.cal-cell.today { outline: 2px solid #1f7a3f; outline-offset: -2px; }
.cal-ev { font-size: 11px; line-height: 1.25; background: #e8f3ec; border-left: 3px solid #1f7a3f; border-radius: 3px; padding: 1px 4px; margin-top: 3px; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cal-ev:hover { background: #d6eadd; }
.row-click { cursor: pointer; }
.row-click:hover td { background: rgba(31, 122, 63, 0.06); }
</style>
