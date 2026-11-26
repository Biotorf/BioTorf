<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useDbStore } from '@/stores/db';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import { useCrmPhotoCovers } from '@/composables/useCrmPhotoCovers';
import CrmRowModal from '@/components/CrmRowModal.vue';
import CrmPhotoGallery from '@/components/photos/CrmPhotoGallery.vue';
import CrmPhotoThumbnail from '@/components/photos/CrmPhotoThumbnail.vue';

const db = useDbStore();
const { canEditCollection } = usePermissions();
const { money } = useFormatters();
const filter = ref('');
const editor = ref(null);
const page = ref(1);
const pageSize = 24;
const visible = computed(() => {
  const query = filter.value.trim().toLowerCase();
  return db.skus.filter((row) => !query || [row.name, row.id, row.line].join(' ').toLowerCase().includes(query));
});
const pageCount = computed(() => Math.max(1, Math.ceil(visible.value.length / pageSize)));
const shownProducts = computed(() => visible.value.slice((page.value - 1) * pageSize, page.value * pageSize));
watch(filter, () => { page.value = 1; });
watch(pageCount, (count) => { page.value = Math.min(page.value, count); });
const { covers, setCover } = useCrmPhotoCovers('skus', () => shownProducts.value.map((product) => product.id));

const readPhotoSelection = () => new URLSearchParams(location.hash.split('?')[1]).get('sku');
const selectedSku = ref(readPhotoSelection());
const product = computed(() => db.skus.find((row) => String(row.id) === selectedSku.value));
const galleryHeading = ref(null);
function productPhotos(id) { return '#/products?' + new URLSearchParams({ sku: id }); }
function syncPhotoSelection() { selectedSku.value = readPhotoSelection(); }
onMounted(() => window.addEventListener('hashchange', syncPhotoSelection));
onBeforeUnmount(() => window.removeEventListener('hashchange', syncPhotoSelection));
watch(galleryHeading, (heading) => {
  heading?.focus({ preventScroll: true });
  heading?.scrollIntoView({ block: 'nearest' });
});

function openPhotosForNewProduct(record) {
  if (!editor.value?.record && record?.id) location.hash = productPhotos(record.id);
}
</script>

<template>
  <section>
    <div class="pagehead">
      <div>
        <h1 data-tour="products-view">Каталог товаров</h1>
        <p class="subtitle">Фасовка, цена и действующая рецептура BioTorf Agro и Home.</p>
      </div>
      <button v-if="canEditCollection('skus')" class="btn primary" data-tour="product-create" @click="editor = { record: null }">Добавить товар</button>
    </div>
    <CrmRowModal
      v-if="editor"
      inline
      :key="editor.record?.id || 'new'"
      coll="skus"
      :record="editor.record"
      @saved="openPhotosForNewProduct"
      @close="editor = null"
    />

    <section v-if="product && !editor" :key="product.id" class="panel product-photos" :aria-label="`Фото товара ${product.name || product.id}`">
      <header class="product-head">
        <h2 ref="galleryHeading" tabindex="-1">{{ product.name || product.id }}</h2>
        <a class="btn slim ghost" href="#/products">Закрыть фото</a>
      </header>
      <CrmPhotoGallery collection="skus" :record-id="String(product.id)" :record-name="product.name"
        :editable="canEditCollection('skus')" @loaded="setCover(product.id, $event)" @changed="setCover(product.id, $event)" />
    </section>

    <div class="toolbar">
      <input v-model="filter" type="search" class="input" aria-label="Поиск товара" placeholder="Название или артикул" />
      <a href="#/registry?table=skus">Полный реестр товаров</a>
    </div>
    <div v-if="visible.length" class="product-grid">
      <article v-for="row in shownProducts" :key="row.id" class="panel product">
        <header class="product-summary">
          <a class="product-cover" :href="productPhotos(row.id)" :aria-label="`Открыть фото товара ${row.name || row.id}`">
            <CrmPhotoThumbnail collection="skus" :record-id="String(row.id)" :cover-id="covers.get(String(row.id))?.id ?? ''">
              <template #fallback><span class="product-photo-empty">Нет фото</span></template>
            </CrmPhotoThumbnail>
          </a>
          <div>
            <div class="product-head">
              <h2>{{ row.name || row.id }}</h2>
              <span v-if="row.line" class="pill">{{ row.line }}</span>
            </div>
            <p class="subtitle">{{ [row.id, row.pack ? row.pack + ' л' : '', row.price != null && row.price !== '' ? money(row.price) : ''].filter(Boolean).join(' · ') }}</p>
          </div>
        </header>
        <p v-if="row.recipeVersion && row.pasteKgPerL > 0">
          Рецептура {{ row.recipeVersion }} · {{ row.pasteKgPerL }} кг пасты на 1 л · потери {{ row.lossPct }}%
        </p>
        <p v-else class="subtitle">Норма расхода пасты ещё не задана.</p>
        <div class="actionbar">
          <a class="btn slim" :href="productPhotos(row.id)" data-tour="product-photos">Фото</a>
          <button v-if="canEditCollection('skus')" class="btn slim ghost" @click="editor = { record: row }">Изменить</button>
        </div>
      </article>
    </div>
    <p v-else class="empty">Товары не найдены.</p>
    <nav v-if="pageCount > 1" class="actionbar product-pages" aria-label="Страницы каталога">
      <button type="button" class="btn slim" :disabled="page === 1" @click="page -= 1">Назад</button>
      <span>Страница {{ page }} из {{ pageCount }}</span>
      <button type="button" class="btn slim" :disabled="page === pageCount" @click="page += 1">Дальше</button>
    </nav>
  </section>
</template>

<style scoped>
.product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 12px; }
.product h2, .product-photos h2 { margin: 0; font-size: 17px; overflow-wrap: anywhere; }
.product-head { display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between; align-items: start; margin-bottom: 4px; }
.product-summary { display: grid; grid-template-columns: 56px minmax(0, 1fr); align-items: center; gap: 10px; }
.product-summary .subtitle { overflow-wrap: anywhere; }
.product-cover { display: grid; place-items: center; aspect-ratio: 1; border-radius: 10px; overflow: hidden; background: var(--surface-soft, #eef5ef); color: var(--muted); text-decoration: none; }
.product-photo-empty { font-size: 10px; }
.product-photos { margin: 0 0 14px; }
.product-photos .product-head { margin-bottom: 12px; }
.product-pages { margin-block-start: 14px; }
</style>
