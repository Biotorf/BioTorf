<script setup>
import { computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import StatCard from '@/components/ui/StatCard.vue';
import StatusPill from '@/components/ui/StatusPill.vue';

const db = useDbStore();
const ui = useUiStore();
const { canEdit } = usePermissions();
const { money, num, day, pillColor } = useFormatters();

const info = computed(() => {
  const paidOrders = db.orders.filter((o) =>
    ['Оплачен', 'Отправлен', 'Доставлен'].includes(o.status)
  );
  const revenue = paidOrders.reduce((a, b) => a + b.amount, 0);
  const liters = paidOrders.reduce((a, b) => a + b.qty * db.skuById(b.sku).pack, 0);
  const pipeline = db.deals
    .filter((d) => !['Оплачено', 'Отгружено', 'Получено клиентом'].includes(d.stage))
    .reduce((a, b) => a + b.amount, 0);
  const pilots = db.pilots.filter(
    (p) => !['Завершен', 'Пилот прекращен'].includes(p.status)
  ).length;

  return [
    ['Выручка по демо-заказам', money(revenue), 'Не подтвержденная выручка компании'],
    ['Продано BIOTORF', num(liters) + ' л', 'Условные оплаченные/отгруженные заказы'],
    ['Открытая воронка', money(pipeline), 'Оценка потенциала сделок'],
    ['Активные пилоты', pilots, 'С учетом протоколов'],
  ];
});
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Панель управления</h1>
        <div class="subtitle">
          Ситуация по компании, критические события и ключевые показатели
        </div>
      </div>
    </div>

    <div class="note">
      <b>Демонстрационный режим.</b> Данные сохраняются только в этом браузере.
    </div>

    <div class="stats">
      <StatCard v-for="[label, value, foot] in info" :key="label" :label="label" :value="value" :foot="foot" />
    </div>

    <div class="dash-grid">
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title">Критические отклонения</div>
        </div>
        <div v-if="db.lateTasks.length === 0" class="empty">Критических просрочек нет</div>
        <div
          v-for="t in db.lateTasks"
          :key="t.id"
          class="insight actionable"
          @click="ui.openWork('task', t.id)"
        >
          <div>
            <b>{{ t.title }}</b>
            <div class="mini">Задача · срок {{ day(t.due) }}</div>
          </div>
          <StatusPill status="Просрочено" />
        </div>
      </section>
    </div>
  </div>
</template>