<script setup>
// «Продукция и цены» + калькуляция себестоимости (демо v0.9). Без бэкенда.
import { computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';

const db = useDbStore();
const { num, money } = useFormatters();
const skus = computed(() => db.data.skus || []);
const cost = computed(() => db.data.cost || {});
const pasteCostL = computed(() => num(cost.value.paste_rub * cost.value.fx_kgs_rub) + (cost.value.inbound_per_l_paste || 0) + (cost.value.local_per_l_paste || 0));
const lines = computed(() => {
  const c = cost.value;
  return [
    { line: 'AGRO', recipe: '1:4', mfg: c.agro_mfg },
    { line: 'HOME', recipe: '1:1', mfg: c.home_mfg },
  ];
});
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Продукция и цены</h1>
        <div class="subtitle">SKU, рецептуры производственных линий и модель себестоимости</div>
      </div>
      <BackendBadge collection="skus" />
    </div>

    <div class="note">Цены и калькуляция — рабочие допущения ({{ cost.source || '—' }}), не утверждённый прайс.</div>

    <section class="panel" style="margin-bottom:16px">
      <div class="panel-title" style="margin-bottom:12px">SKU продукции</div>
      <table class="table">
        <thead><tr><th>Артикул</th><th>Название</th><th>Линейка</th><th>Фасовка, л</th><th>Рецептура (паста:вода)</th><th>Статус</th></tr></thead>
        <tbody>
          <tr v-for="s in skus" :key="s.id">
            <td><b>{{ s.id }}</b></td><td>{{ s.name }}</td>
            <td><span class="chip">{{ s.line }}</span></td>
            <td>{{ num(s.pack) }}</td><td>{{ s.recipe }}</td><td>{{ s.status }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <div class="cards2">
      <section class="panel">
        <div class="panel-title" style="margin-bottom:12px">Модель себестоимости</div>
        <dl class="details-grid">
          <div class="detail"><dt>Паста, ₽/кг</dt><dd>{{ num(cost.paste_rub) }} ₽</dd></div>
          <div class="detail"><dt>Курс ₽→сом</dt><dd>{{ num(cost.fx_kgs_rub) }}</dd></div>
          <div class="detail"><dt>Импорт на 1 л пасты</dt><dd>{{ money(cost.inbound_per_l_paste) }}</dd></div>
          <div class="detail"><dt>Локальные расходы на 1 л</dt><dd>{{ money(cost.local_per_l_paste) }}</dd></div>
          <div class="detail"><dt>Производство AGRO, сом/л</dt><dd>{{ money(cost.agro_mfg) }}</dd></div>
          <div class="detail"><dt>Производство HOME, сом/л</dt><dd>{{ money(cost.home_mfg) }}</dd></div>
          <div class="detail"><dt>Постоянные расходы, мес</dt><dd>{{ money(cost.fixed_month) }}</dd></div>
          <div class="detail"><dt>Сценарный объем, л/мес</dt><dd>{{ num(cost.scenario_volume) }} л</dd></div>
        </dl>
      </section>
      <section class="panel">
        <div class="panel-title" style="margin-bottom:12px">Линейки</div>
        <div v-for="l in lines" :key="l.line" class="insight">
          <div><b>{{ l.line }}</b><div class="mini">Рецептура {{ l.recipe }} · производство {{ money(l.mfg) }}/л</div></div>
          <span class="pill">{{ skus.filter(s => s.line === l.line).length }} SKU</span>
        </div>
        <div class="mini" style="margin-top:12px">Расчётная стоимость 1 л пасты с логистикой ≈ {{ money(pasteCostL) }}. Нормы внесения на поле утверждает агроном.</div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.mini { font-size: 12px; color: var(--muted, #7b8a86); }
</style>
