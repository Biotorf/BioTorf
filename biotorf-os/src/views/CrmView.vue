<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import CrmImportModal from '@/components/CrmImportModal.vue';
import StatusPill from '@/components/ui/StatusPill.vue';
import ClientCardModal from '@/views/ClientCardModal.vue';

const db = useDbStore();
const ui = useUiStore();
const { day } = useFormatters();
const { canSeeFarm, canEditCollection } = usePermissions();

function clientIdFromUrl() {
  return new URLSearchParams(location.hash.split('?')[1]).get('client');
}

const selected = ref(clientIdFromUrl());
function readClientId() { selected.value = clientIdFromUrl(); }
onMounted(() => window.addEventListener('hashchange', readClientId));
onUnmounted(() => window.removeEventListener('hashchange', readClientId));
function clientLink(id) { return '#/crm?' + new URLSearchParams({ client: id }); }

const category = ref('all');
const clientTypes = [
  'Частный покупатель', 'Компания', 'Агропроизводитель', 'Розничный магазин',
  'Оптовая база', 'Дилер', 'Дистрибьютор', 'Другой',
];
const personTypes = new Set(['частный покупатель', 'физическое лицо', 'физлицо', 'частное лицо']);
const contactsByClient = computed(() => {
  const result = new Map();
  for (const contact of db.data.contacts || []) {
    const entries = result.get(contact.farmId) || [];
    entries.push(contact);
    result.set(contact.farmId, entries);
  }
  return result;
});
function customerPhone(client) {
  const contacts = contactsByClient.value.get(client.id) || [];
  return client.phone || contacts.find((contact) => contact.primary && contact.phone)?.phone ||
    contacts.find((contact) => contact.phone)?.phone;
}
const customers = computed(() => {
  const query = ui.search.trim().toLowerCase();
  const digits = query.replace(/\D/g, '');
  return db.farms.filter(canSeeFarm).filter((client) => {
    const type = String(client.type || '').trim().toLowerCase();
    const person = personTypes.has(type);
    if (category.value === 'person' && !person) return false;
    if (category.value === 'company' && (person || !type)) return false;
    const contacts = contactsByClient.value.get(client.id) || [];
    const phone = customerPhone(client);
    return !query ||
      [client.name, client.owner, client.region, client.type, phone, ...contacts.map((c) => c.name)]
        .some((value) => String(value || '').toLowerCase().includes(query)) ||
      (digits.length >= 3 && [phone, ...contacts.map((c) => c.phone)]
        .some((value) => String(value || '').replace(/\D/g, '').includes(digits)));
  }).sort((first, second) => {
    const dateOrder = String(first.next || '9999').localeCompare(String(second.next || '9999'));
    return dateOrder || String(first.name || first.id).localeCompare(String(second.name || second.id), 'ru');
  });
});
const page = ref(1);
const pageSize = 36;
const pageCount = computed(() => Math.ceil(customers.value.length / pageSize));
const shownCustomers = computed(() => customers.value.slice((page.value - 1) * pageSize, page.value * pageSize));
watch([category, () => ui.search], () => { page.value = 1; });
watch(pageCount, (value) => { if (page.value > value) page.value = Math.max(1, value); });

const importing = ref('');
const creating = ref(false);
const saving = ref(false);
const createError = ref('');
const detail = ref({ name: '', type: '', phone: '' });
function openCreate() {
  detail.value = { name: '', type: '', phone: '' };
  createError.value = '';
  creating.value = true;
}
async function createClient() {
  if (saving.value) return;
  const name = detail.value.name.trim();
  if (!name) return;
  saving.value = true;
  createError.value = '';
  try {
    const id = db.uid('F');
    await db.importCollection('farms', [{
      id, name, type: detail.value.type, phone: detail.value.phone.trim(),
      owner: ui.name || ui.login, status: 'Активный',
    }], 'merge');
    creating.value = false;
    location.hash = clientLink(id);
  } catch (error) {
    createError.value = error.message || 'Не удалось сохранить клиента.';
  } finally {
    saving.value = false;
  }
}

function initials(name) {
  return String(name || '').trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'К';
}
</script>

<template>
  <section class="clients-view">
    <template v-if="selected">
      <nav class="clients-crumb" aria-label="Навигация по клиентам">
        <a href="#/crm">← Все клиенты</a>
      </nav>
      <ClientCardModal :key="selected" :farm-id="selected" embedded />
    </template>
    <template v-else>
      <header class="pagehead">
        <div>
          <h1>Клиенты</h1>
          <p class="subtitle">Контакты, история общения и продажи</p>
        </div>
        <div class="actionbar">
          <BackendBadge collection="farms" />
          <button v-if="canEditCollection('farms')" class="btn primary" @click="openCreate">＋ Новый клиент</button>
        </div>
      </header>

      <form v-if="creating" class="panel create-client" @submit.prevent="createClient">
        <h2>Новый клиент</h2>
        <div class="create-fields">
          <label class="field">Имя или название
            <input v-model="detail.name" required class="input" placeholder="Например, ОсОО «Агро Плюс»" />
          </label>
          <label class="field">Тип клиента
            <select v-model="detail.type" class="select" aria-label="Тип нового клиента">
              <option value="">Выбрать позже</option>
              <option v-for="type in clientTypes" :key="type">{{ type }}</option>
            </select>
          </label>
          <label class="field">Телефон
            <input v-model="detail.phone" type="tel" autocomplete="tel" class="input" placeholder="+996" />
          </label>
        </div>
        <p v-if="createError" role="alert" class="danger-text">{{ createError }}</p>
        <div class="actionbar">
          <button type="button" class="btn ghost" :disabled="saving" @click="creating = false">Отмена</button>
          <button class="btn primary" :disabled="saving || !detail.name.trim()">{{ saving ? 'Сохраняем…' : 'Создать карточку' }}</button>
        </div>
      </form>

      <div class="client-list-tools">
        <input v-model="ui.search" type="search" class="input" aria-label="Поиск клиентов" placeholder="Имя, компания, телефон…" />
        <select v-model="category" class="select" aria-label="Тип клиента">
          <option value="all">Все клиенты</option>
          <option value="company">Компании и хозяйства</option>
          <option value="person">Частные лица</option>
        </select>
      </div>

      <ul v-if="customers.length" class="customer-grid" aria-label="Карточки клиентов">
        <li v-for="client in shownCustomers" :key="client.id">
          <a :href="clientLink(client.id)" class="customer-tile">
            <div class="customer-tile-head">
              <span class="customer-avatar" aria-hidden="true">{{ initials(client.name) }}</span>
              <div>
                <h2>{{ client.name || client.id }}</h2>
                <p>{{ [client.type, client.region].filter(Boolean).join(' · ') || 'Карточка клиента' }}</p>
              </div>
            </div>
            <dl class="customer-info">
              <div v-if="customerPhone(client)"><dt>Телефон</dt><dd>{{ customerPhone(client) }}</dd></div>
              <div v-if="client.owner"><dt>Менеджер</dt><dd>{{ client.owner }}</dd></div>
              <div v-if="client.next"><dt>Следующий контакт</dt><dd>{{ day(client.next) }}</dd></div>
            </dl>
            <div class="customer-tile-foot">
              <StatusPill v-if="client.status" :status="client.status" />
              <span>Открыть карточку <span aria-hidden="true">→</span></span>
            </div>
          </a>
        </li>
      </ul>
      <div v-else class="empty">
        {{ ui.search || category !== 'all' ? 'По выбранным условиям клиентов нет.' : 'Пока нет клиентов.' }}
      </div>
      <nav v-if="pageCount > 1" class="customer-pagination" aria-label="Страницы списка клиентов">
        <button class="btn slim" :disabled="page === 1" @click="page -= 1">Назад</button>
        <span>Страница {{ page }} из {{ pageCount }}</span>
        <button class="btn slim" :disabled="page === pageCount" @click="page += 1">Дальше</button>
      </nav>
      <details class="client-table-tools">
        <summary>Реестры и импорт</summary>
        <div class="actionbar">
          <a class="btn slim" href="#/registry?table=farms">Реестр клиентов</a>
          <a class="btn slim" href="#/registry?table=leads">Реестр обращений</a>
          <button v-if="canEditCollection('farms')" class="btn slim" @click="importing = 'farms'">Импорт клиентов</button>
          <button v-if="canEditCollection('leads')" class="btn slim" @click="importing = 'leads'">Импорт обращений</button>
        </div>
      </details>
      <CrmImportModal v-if="importing" :coll="importing" @close="importing = ''" />
    </template>
  </section>
</template>

<style scoped>
.clients-crumb { margin: 0 0 12px; }
.clients-crumb a { color: var(--accent-dark, #226f40); text-decoration: none; font-weight: 650; }
.create-client { padding: 16px; margin-bottom: 16px; }
.create-client h2 { margin: 0 0 12px; font-size: 17px; }
.create-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 12px; }
.client-list-tools { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 16px; }
.client-list-tools .input { max-width: 330px; }
.client-table-tools { margin-top: 17px; }
.client-table-tools summary { cursor: pointer; color: #52665b; margin-bottom: 8px; }
.client-list-tools .select { width: auto; }
.customer-pagination { display: flex; align-items: center; justify-content: center; gap: 10px; margin-top: 14px; }
.customer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 12px; margin: 0; padding: 0; list-style: none; }
.customer-tile { display: flex; flex-direction: column; gap: 14px; height: 100%; padding: 16px; text-decoration: none; color: inherit; background: #fff; border: 1px solid #dce9de; border-radius: 14px; box-shadow: 0 1px 2px #122a1d0a; }
.customer-tile:hover, .customer-tile:focus-visible { border-color: #5aa978; }
.customer-tile-head, .customer-tile-foot { display: flex; gap: 10px; align-items: center; }
.customer-tile-head h2 { font-size: 16px; margin: 0; overflow-wrap: anywhere; }
.customer-tile-head p { margin: 3px 0 0; font-size: 12px; color: #52665b; }
.customer-tile-foot { margin-top: auto; font-size: 12px; }
.customer-tile-foot > span:last-child { margin-left: auto; font-weight: 650; color: #226f40; }
.customer-avatar { flex: 0 0 38px; min-height: 38px; display: grid; place-items: center; border-radius: 10px; background: #e8f5eb; color: #24703e; font-weight: 750; }
.customer-info { display: grid; gap: 6px; margin: 0; font-size: 13px; }
.customer-info div { display: flex; flex-wrap: wrap; gap: 4px 8px; justify-content: space-between; }
.customer-info dt { color: #52665b; }
.customer-info dd { margin: 0; overflow-wrap: anywhere; }
</style>
