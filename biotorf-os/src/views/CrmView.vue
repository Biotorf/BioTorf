<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { useCrmPhotoCovers } from '@/composables/useCrmPhotoCovers';
import { clientInitials, isPerson, phoneDigits, primaryContact } from '@/data/clientDesk';
import { statusOptions } from '@/data/crmFields';
import { useFormatters } from '@/composables/useFormatters';
import BackendBadge from '@/components/ui/BackendBadge.vue';
import CrmDataTable from '@/components/CrmDataTable.vue';
import CrmImportModal from '@/components/CrmImportModal.vue';
import CrmSelectField from '@/components/CrmSelectField.vue';
import CrmPhotoThumbnail from '@/components/photos/CrmPhotoThumbnail.vue';
import StatusPill from '@/components/ui/StatusPill.vue';
import ClientCardModal from '@/views/ClientCardModal.vue';

const db = useDbStore();
const ui = useUiStore();
const { day } = useFormatters();
const { canSeeFarm, canEditCollection } = usePermissions();

function routeQuery() { return new URLSearchParams(location.hash.split('?')[1]); }
const selected = ref(routeQuery().get('client'));
function clientLink(id) { return '#/crm?' + new URLSearchParams({ client: id }); }

const category = ref('all');
const owner = ref('');
const status = ref('');
const sortBy = ref('next');
const SEARCH_MODE_KEY = 'biotorf.clients.layout';
let storedMode;
try { storedMode = localStorage.getItem(SEARCH_MODE_KEY); } catch { /* storage disabled */ }
const mode = ref(storedMode === 'list' ? 'list' : 'cards');
watch(mode, (value) => {
  try { localStorage.setItem(SEARCH_MODE_KEY, value); } catch { /* storage disabled */ }
});
const visibleClients = computed(() => db.farms.filter(canSeeFarm));
const owners = computed(() => [...new Set(visibleClients.value.map((client) => client.owner).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), 'ru')));
const statuses = computed(() => statusOptions('farms', visibleClients.value));
const contactsByClient = computed(() => {
  const result = new Map();
  for (const contact of db.data.contacts || []) {
    const entries = result.get(contact.farmId) || [];
    entries.push(contact);
    result.set(contact.farmId, entries);
  }
  return result;
});
const clientInfo = computed(() => {
  const profiles = new Map();
  for (const client of visibleClients.value) {
    const contacts = contactsByClient.value.get(client.id) || [];
    const primary = primaryContact(contacts);
    const phone = client.phone || primary?.phone || contacts.find((contact) => contact.phone)?.phone;
    profiles.set(client.id, { contacts, primary, phone, email: client.email || primary?.email });
  }
  return profiles;
});
const customers = computed(() => {
  const query = ui.search.trim().toLowerCase();
  const digits = phoneDigits(query);
  const includesQuery = (value) => String(value || '').toLowerCase().includes(query);
  return visibleClients.value.filter((client) => {
    const person = isPerson(client.type);
    if (category.value === 'person' && !person) return false;
    if (category.value === 'company' && (person || !client.type)) return false;
    if (owner.value && client.owner !== owner.value) return false;
    if (status.value && client.status !== status.value) return false;
    if (!query) return true;
    const { phone, email, contacts } = clientInfo.value.get(client.id);
    return [client.name, client.owner, client.region, client.type, client.taxId, phone, email]
      .some(includesQuery) || contacts.some((contact) =>
      [contact.name, contact.phone, contact.email].some(includesQuery)) ||
      (digits.length >= 3 && [phone, ...contacts.map((contact) => contact.phone)]
        .some((value) => phoneDigits(value).includes(digits)));
  }).sort((first, second) => {
    const nameOrder = String(first.name || first.id).localeCompare(String(second.name || second.id), 'ru');
    if (sortBy.value === 'name') return nameOrder;
    if (sortBy.value === 'updated') {
      return String(second._updatedAt || second.createdAt || '').localeCompare(String(first._updatedAt || first.createdAt || '')) || nameOrder;
    }
    return String(first.next || '9999').localeCompare(String(second.next || '9999')) || nameOrder;
  });
});
const page = ref(1);
const pageSize = 36;
const clientColumns = ['name', 'type', 'region', 'phone', 'email', 'owner', 'next', 'status'];
const pageCount = computed(() => Math.ceil(customers.value.length / pageSize));
const shownCustomers = computed(() => customers.value.slice((page.value - 1) * pageSize, page.value * pageSize));
const { covers } = useCrmPhotoCovers('farms', () => selected.value ? [] : shownCustomers.value.map((client) => client.id));
watch([category, owner, status, sortBy, () => ui.search], () => { page.value = 1; });
watch(pageCount, (value) => { if (page.value > value) page.value = Math.max(1, value); });

const importing = ref('');
const creating = ref(false);
const saving = ref(false);
const createError = ref('');
const detail = ref({});
function openCreate() {
  if (!canEditCollection('farms') || creating.value) return;
  detail.value = { name: '', type: '', phone: '', email: '', region: '', address: '', taxId: '', source: '', notes: '', next: '' };
  createError.value = '';
  creating.value = true;
}
function readRoute() {
  const route = routeQuery();
  selected.value = route.get('client');
  if (!selected.value && route.get('new') === '1') openCreate();
  else creating.value = false;
}
onMounted(() => {
  readRoute();
  window.addEventListener('hashchange', readRoute);
});
onUnmounted(() => window.removeEventListener('hashchange', readRoute));
function startCreate() { location.hash = '#/crm?new=1'; }
function cancelCreate() { location.hash = '#/crm'; }

const match = computed(() => {
  const phone = phoneDigits(detail.value.phone);
  const email = detail.value.email?.trim().toLowerCase();
  if (phone.length < 7 && !email) return null;
  return visibleClients.value.find((client) => {
    const profile = clientInfo.value.get(client.id);
    return (phone.length >= 7 && [profile.phone, ...profile.contacts.map((contact) => contact.phone)]
      .some((value) => phoneDigits(value) === phone)) ||
      (email && [profile.email, ...profile.contacts.map((contact) => contact.email)]
        .some((value) => String(value || '').trim().toLowerCase() === email));
  });
});
async function createClient() {
  if (saving.value || !canEditCollection('farms')) return;
  const name = detail.value.name.trim();
  if (!name) return;
  saving.value = true;
  createError.value = '';
  try {
    const id = db.uid('F');
    const values = Object.fromEntries(Object.entries(detail.value).map(([key, value]) => [key, value.trim()])
      .filter(([, value]) => value));
    await db.importCollection('farms', [{
      ...values, id, name, owner: ui.name || ui.login, status: 'Активный', createdAt: new Date().toISOString(),
    }], 'merge');
    creating.value = false;
    location.hash = clientLink(id);
  } catch (error) {
    createError.value = error.message || 'Не удалось сохранить клиента.';
  } finally {
    saving.value = false;
  }
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
          <button v-if="canEditCollection('farms')" class="btn primary" data-tour="client-create" @click="startCreate">＋ Новый клиент</button>
        </div>
      </header>

      <form v-if="creating" class="panel create-client" @submit.prevent="createClient">
        <h2>Новый клиент</h2>
        <div class="create-fields">
          <label class="field">Имя или название
            <input v-model="detail.name" required class="input" placeholder="Например, ОсОО «Агро Плюс»" />
          </label>
          <CrmSelectField v-model="detail.type" label="Тип клиента" :options="db.optionsFor('types', 'farms', 'type')" list-key="types" />
          <label class="field">Телефон
            <input v-model="detail.phone" type="tel" autocomplete="tel" class="input" placeholder="+996" />
          </label>
        </div>
        <details class="more-client-fields">
          <summary>Дополнительные данные</summary>
          <div class="create-fields">
            <label class="field">E-mail <input v-model="detail.email" class="input" type="email" autocomplete="email" /></label>
            <CrmSelectField v-model="detail.region" label="Регион" :options="db.optionsFor('regions', 'farms', 'region')" list-key="regions" />
            <label class="field">ИНН <input v-model="detail.taxId" class="input" inputmode="numeric" /></label>
            <label class="field">Адрес <input v-model="detail.address" class="input" autocomplete="street-address" /></label>
            <CrmSelectField v-model="detail.source" label="Источник" :options="db.optionsFor('sources', 'farms', 'source')" list-key="sources" />
            <label class="field">Связаться <input v-model="detail.next" class="input" type="date" /></label>
            <label class="field detailed-note">Заметки <textarea v-model="detail.notes" class="input" rows="2" /></label>
          </div>
        </details>
        <p v-if="match" class="duplicate-hint">Похожий контакт уже есть. <a :href="clientLink(match.id)">{{ match.name }}</a></p>
        <p v-if="createError" role="alert" class="danger-text">{{ createError }}</p>
        <div class="actionbar">
          <button type="button" class="btn ghost" :disabled="saving" @click="cancelCreate">Отмена</button>
          <button class="btn primary" :disabled="saving || !detail.name.trim()">{{ saving ? 'Сохраняем…' : 'Создать карточку' }}</button>
        </div>
      </form>

      <section class="customer-directory" data-tour="client-directory" aria-label="Фильтры клиентов">
        <div class="client-list-tools">
          <input v-model="ui.search" type="search" class="input" aria-label="Поиск клиентов" placeholder="Имя, компания, телефон, e-mail…" />
          <select v-model="category" class="select" aria-label="Фильтр по типу клиента">
            <option value="all">Все типы</option>
            <option value="company">Компании и хозяйства</option>
            <option value="person">Частные лица</option>
          </select>
          <select v-model="owner" class="select" aria-label="Менеджер">
            <option value="">Все менеджеры</option>
            <option v-for="name in owners" :key="name">{{ name }}</option>
          </select>
          <select v-model="status" class="select" aria-label="Статус клиента">
            <option value="">Все статусы</option>
            <option v-for="value in statuses" :key="value">{{ value }}</option>
          </select>
        </div>
        <div class="directory-tools">
          <span class="mini" aria-live="polite">Найдено {{ customers.length }} из {{ visibleClients.length }}</span>
          <div class="view-tools">
            <select v-model="sortBy" class="select sort" aria-label="Сортировка">
              <option value="next">По дате контакта</option>
              <option value="name">По имени</option>
              <option value="updated">Недавно изменённые</option>
            </select>
            <div class="display-choice" aria-label="Вид списка">
              <button type="button" :aria-pressed="mode === 'cards'" @click="mode = 'cards'">Карточки</button>
              <button type="button" :aria-pressed="mode === 'list'" @click="mode = 'list'">Список</button>
            </div>
          </div>
        </div>
      </section>

      <ul v-if="customers.length && mode === 'cards'" class="customer-grid" aria-label="Карточки клиентов">
        <li v-for="client in shownCustomers" :key="client.id">
          <a :href="clientLink(client.id)" class="customer-tile" data-tour="client-card-link">
            <div class="customer-tile-head">
              <span class="customer-avatar" aria-hidden="true">
                <CrmPhotoThumbnail collection="farms" :record-id="String(client.id)" :cover-id="covers.get(String(client.id))?.id ?? ''">
                  <template #fallback>{{ clientInitials(client.name) }}</template>
                </CrmPhotoThumbnail>
              </span>
              <div>
                <h2>{{ client.name || client.id }}</h2>
                <p v-if="client.type || client.region">{{ [client.type, client.region].filter(Boolean).join(' · ') }}</p>
              </div>
            </div>
            <dl class="customer-info">
              <div v-if="clientInfo.get(client.id).phone"><dt>Телефон</dt><dd>{{ clientInfo.get(client.id).phone }}</dd></div>
              <div v-if="clientInfo.get(client.id).email"><dt>E-mail</dt><dd>{{ clientInfo.get(client.id).email }}</dd></div>
              <div v-if="clientInfo.get(client.id).primary?.name"><dt>Контакт</dt><dd>{{ clientInfo.get(client.id).primary.name }}</dd></div>
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
      <CrmDataTable v-else-if="customers.length" coll="farms" :rows="shownCustomers" :columns="clientColumns">
        <template #name="{ row: client }">
          <a :href="clientLink(client.id)" class="client-name client-name-with-photo" data-tour="client-card-link">
            <span class="customer-avatar list-avatar" aria-hidden="true">
              <CrmPhotoThumbnail collection="farms" :record-id="String(client.id)" :cover-id="covers.get(String(client.id))?.id ?? ''">
                <template #fallback>{{ clientInitials(client.name) }}</template>
              </CrmPhotoThumbnail>
            </span>
            {{ client.name || client.id }}
          </a>
        </template>
        <template #phone="{ row: client }">
          <a v-if="clientInfo.get(client.id).phone" :href="'tel:' + clientInfo.get(client.id).phone">{{ clientInfo.get(client.id).phone }}</a>
          <span v-else>—</span>
        </template>
        <template #email="{ row: client }">
          <a v-if="clientInfo.get(client.id).email" :href="'mailto:' + clientInfo.get(client.id).email">{{ clientInfo.get(client.id).email }}</a>
          <span v-else>—</span>
        </template>
        <template #next="{ row: client }">{{ client.next ? day(client.next) : '—' }}</template>
      </CrmDataTable>
      <div v-else class="empty">
        {{ ui.search || category !== 'all' || owner || status ? 'По выбранным условиям клиентов нет.' : 'Пока нет клиентов.' }}
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

.customer-directory { background: #fff; border: 1px solid #dce9de; border-radius: 14px; padding: 12px; margin-bottom: 14px; }
.client-list-tools, .directory-tools, .view-tools { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.directory-tools { justify-content: space-between; border-top: 1px solid #edf2ef; margin-top: 12px; padding-top: 8px; }
.view-tools .sort { width: auto; font-size: 13px; max-width: 100%; }
.display-choice { display: flex; border: 1px solid #dce9de; border-radius: 9px; padding: 2px; }
.display-choice button { border: 0; border-radius: 6px; padding: 5px 9px; color: #52665b; background: #fff; font-size: 13px; }
.display-choice button[aria-pressed="true"] { color: #176548; background: #e6f3eb; font-weight: 650; }
.more-client-fields { margin: 0 0 12px; }
.more-client-fields summary { cursor: pointer; color: #286749; margin-bottom: 8px; }
.detailed-note { grid-column: 1 / -1; }
.duplicate-hint { background: #fff8e9; color: #7b5a1b; border-radius: 8px; padding: 8px; }
.client-name { text-decoration: none; font-weight: 700; }
.client-list-tools .input { max-width: 330px; }
.client-table-tools { margin-top: 17px; }
.client-table-tools summary { cursor: pointer; color: #52665b; margin-bottom: 8px; }
.client-list-tools .select { width: auto; }
.customer-pagination { display: flex; align-items: center; justify-content: center; gap: 10px; margin-top: 14px; }
.customer-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 265px), 1fr)); gap: 12px; margin: 0; padding: 0; list-style: none; }
.customer-tile { display: flex; flex-direction: column; gap: 14px; height: 100%; padding: 16px; text-decoration: none; color: inherit; background: #fff; border: 1px solid #dce9de; border-radius: 14px; box-shadow: 0 1px 2px #122a1d0a; }
.customer-tile:hover, .customer-tile:focus-visible { border-color: #5aa978; }
.customer-tile-head, .customer-tile-foot { display: flex; gap: 10px; align-items: center; }
.customer-tile-head h2 { font-size: 16px; margin: 0; overflow-wrap: anywhere; }
.customer-tile-head p { margin: 3px 0 0; font-size: 12px; color: #52665b; }
.customer-tile-foot { margin-top: auto; font-size: 12px; }
.customer-tile-foot > span:last-child { margin-left: auto; font-weight: 650; color: #226f40; }
.customer-avatar { flex: 0 0 38px; min-height: 38px; display: grid; place-items: center; border-radius: 10px; overflow: hidden; background: var(--accent-soft, #e8f5eb); color: var(--accent-ink, #24703e); font-weight: 750; }
.client-name-with-photo { display: inline-flex; align-items: center; gap: 8px; }
.list-avatar { flex-basis: 28px; min-height: 28px; inline-size: 28px; border-radius: 7px; font-size: 12px; }
.customer-info { display: grid; gap: 6px; margin: 0; font-size: 13px; }
.customer-info div { display: flex; flex-wrap: wrap; gap: 4px 8px; justify-content: space-between; }
.customer-info dt { color: #52665b; }
.customer-info dd { margin: 0; overflow-wrap: anywhere; }

@media (max-width: 600px) {
  .client-list-tools .input { max-width: none; flex-basis: 100%; }
  .client-list-tools .select { flex: 1; min-width: 110px; }
  .directory-tools { align-items: flex-start; }
}
</style>
