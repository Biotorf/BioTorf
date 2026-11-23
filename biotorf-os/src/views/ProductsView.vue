<script setup>
import { computed, ref } from 'vue';
import { useDbStore } from '@/stores/db';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import CrmRowModal from '@/components/CrmRowModal.vue';

const db = useDbStore();
const { canEditCollection } = usePermissions();
const { money } = useFormatters();
const filter = ref('');
const editor = ref(null);
const visible = computed(() => {
  const query = filter.value.trim().toLowerCase();
  return db.skus.filter((row) => !query || [row.name, row.id, row.line].join(' ').toLowerCase().includes(query));
});
</script>

<template>
  <section>
    <div class="pagehead">
      <div>
        <h1>Каталог товаров</h1>
        <p class="subtitle">Фасовка, цена и действующая рецептура BioTorf Agro и Home.</p>
      </div>
      <button v-if="canEditCollection('skus')" class="btn primary" @click="editor = { record: null }">Добавить товар</button>
    </div>
    <CrmRowModal
      v-if="editor"
      inline
      :key="editor.record?.id || 'new'"
      coll="skus"
      :record="editor.record"
      @close="editor = null"
    />

    <div class="toolbar">
      <input v-model="filter" type="search" class="input" aria-label="Поиск товара" placeholder="Название или артикул" />
      <a href="#/registry?table=skus">Полный реестр товаров</a>
    </div>
    <div v-if="visible.length" class="product-grid">
      <article v-for="row in visible" :key="row.id" class="panel product">
        <div class="product-head">
          <h2>{{ row.name }}</h2>
          <span v-if="row.line" class="pill">{{ row.line }}</span>
        </div>
        <p class="subtitle">{{ [row.id, row.pack ? row.pack + ' л' : '', row.price != null && row.price !== '' ? money(row.price) : ''].filter(Boolean).join(' · ') }}</p>
        <p v-if="row.recipeVersion && row.powderKgPerL > 0">
          Рецептура {{ row.recipeVersion }} · {{ row.powderKgPerL }} кг порошка на 1 л · потери {{ row.lossPct }}%
        </p>
        <p v-else class="subtitle">Норма расхода порошка ещё не задана.</p>
        <button v-if="canEditCollection('skus')" class="btn slim" @click="editor = { record: row }">Изменить</button>
      </article>
    </div>
    <p v-else class="empty">Товары не найдены.</p>
  </section>
</template>

<style scoped>
.product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 12px; }
.product h2 { font-size: 17px; }
.product-head { display: flex; gap: 8px; justify-content: space-between; align-items: start; margin-bottom: 4px; }
</style>
