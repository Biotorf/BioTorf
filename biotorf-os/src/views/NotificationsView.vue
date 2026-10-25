<script setup>
// «Уведомления» (руководство v0.9 §7): просроченные задачи, контакты без
// действия, контроль пилотов, неоплаченные счета. Клик — переход к объекту.
import { computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { useFormatters } from '@/composables/useFormatters';

const db = useDbStore();
const ui = useUiStore();
const { day, money } = useFormatters();

const isLate = (d) => d && new Date(d + 'T23:59:59') < new Date();

const items = computed(() => {
  const out = [];
  for (const t of db.tasks) {
    if (t.status !== 'Выполнена' && isLate(t.due))
      out.push({ sev: 'red', title: `Просрочена задача: ${t.title}`, meta: `Исполнитель ${t.owner} · срок ${day(t.due)}`, open: () => ui.openRecord('task', t.id) });
  }
  for (const f of db.farms) {
    if (isLate(f.next))
      out.push({ sev: 'amber', title: `Контакт без действия: ${f.name}`, meta: `Хозяйство · следующий контакт был ${day(f.next)}`, open: () => ui.openClient(f.id) });
  }
  for (const l of db.leads) {
    if (['Новый лид', 'В работе'].includes(l.status) && isLate(l.next))
      out.push({ sev: 'amber', title: `Лид без действия: ${l.name}`, meta: `${l.owner} · срок был ${day(l.next)}`, open: () => ui.openLeadCard(l.id) });
  }
  for (const p of db.pilots) {
    if (!['Завершен', 'Пилот прекращен'].includes(p.status) && isLate(p.nextCheck || p.next))
      out.push({ sev: 'amber', title: `Контроль пилота: ${p.title || p.id}`, meta: `Агрономия · проверка по плану ${day(p.nextCheck || p.next)}`, open: () => ui.openRecord('pilot', p.id) });
  }
  for (const inv of db.invoices) {
    if (!inv.paid && inv.status !== 'Оплачен' && inv.status !== 'Отменён')
      out.push({ sev: 'red', title: `Неоплаченный счёт ${inv.number}`, meta: `${money(inv.amount)} · выставлен ${day((inv.date || '').slice(0, 10))}`, open: () => ui.openRecord('invoice', inv.id) });
  }
  return out;
});

function open(it) { it.open(); }
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Уведомления</h1>
        <div class="subtitle">События, требующие внимания: {{ items.length }}</div>
      </div>
    </div>

    <section class="panel">
      <div v-if="!items.length" class="empty">Все задачи в графике — уведомлений нет 👍</div>
      <div v-for="(it, i) in items" :key="i" class="insight actionable" @click="open(it)">
        <span class="dot" :style="{ background: it.sev === 'red' ? '#c62828' : '#e08a00' }"></span>
        <div><b>{{ it.title }}</b><div class="mini">{{ it.meta }}</div></div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
</style>
