<script setup>
import { ref, computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';

const props = defineProps({ farmId: { type: String, required: true } });
const db = useDbStore();
const { num, day, money } = useFormatters();

const tabs = ['overview', 'contacts', 'deals', 'pilots', 'orders', 'history'];
const active = ref('overview');

const farm = computed(() => db.farmById(props.farmId));
const contacts = computed(() => db.data.contacts.filter((c) => c.farmId === props.farmId));
const deals = computed(() => db.deals.filter((d) => d.farmId === props.farmId));
const pilots = computed(() => db.pilots.filter((p) => p.farmId === props.farmId));
const orders = computed(() => db.orders.filter((o) => o.farmId === props.farmId));
</script>

<template>
  <div v-if="farm">
    <div class="client-hero">
      <div>
        <div class="mini">КАРТОЧКА КЛИЕНТА · {{ farm.id }}</div>
        <h3>{{ farm.name }}</h3>
        <div class="mini">{{ farm.region }} · {{ farm.crop }} · {{ num(farm.area) }} га</div>
      </div>
      <StatusPill :status="farm.status" />
    </div>

    <div class="client-tabs">
      <button
        v-for="t in tabs"
        :key="t"
        class="client-tab"
        :class="{ selected: active === t }"
        @click="active = t"
      >
        {{ { overview: 'Обзор', contacts: 'Контакты', deals: 'Сделки', pilots: 'Испытания', orders: 'Заказы', history: 'История' }[t] }}
      </button>
    </div>

    <div v-if="active === 'overview'" class="details-grid">
      <dl class="detail"><dt>Тип</dt><dd>{{ farm.type }}</dd></dl>
      <dl class="detail"><dt>Менеджер</dt><dd>{{ farm.owner }}</dd></dl>
      <dl class="detail"><dt>Следующий контакт</dt><dd>{{ day(farm.next) }}</dd></dl>
      <dl class="detail"><dt>Площадь</dt><dd>{{ num(farm.area) }} га</dd></dl>
    </div>

    <div v-if="active === 'deals'">
      <div v-for="d in deals" :key="d.id" class="insight">
        <div><b>{{ d.title }}</b><div class="mini">{{ d.stage }}</div></div>
        <b>{{ money(d.amount) }}</b>
      </div>
      <div v-if="!deals.length" class="empty">Сделок нет</div>
    </div>

    <div v-if="active === 'pilots'">
      <div v-for="p in pilots" :key="p.id" class="insight">
        <div><b>{{ p.crop }}</b><div class="mini">{{ p.id }} · {{ num(p.area) }} га</div></div>
        <StatusPill :status="p.status" />
      </div>
      <div v-if="!pilots.length" class="empty">Испытаний нет</div>
    </div>

    <div v-if="active === 'orders'">
      <div v-for="o in orders" :key="o.id" class="insight">
        <div><b>{{ o.id }}</b><div class="mini">{{ o.status }}</div></div>
        <b>{{ money(o.amount) }}</b>
      </div>
      <div v-if="!orders.length" class="empty">Заказов нет</div>
    </div>
  </div>
</template>