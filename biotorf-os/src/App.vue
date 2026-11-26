<script setup>
import { computed, nextTick, provide, ref, defineAsyncComponent, markRaw, onMounted, onBeforeUnmount } from 'vue';
import { useUiStore } from '@/stores/ui';
import { useDbStore } from '@/stores/db';
import AppSidebar from '@/components/layout/AppSidebar.vue';
import AppTopbar from '@/components/layout/AppTopbar.vue';
import GuidedTraining from '@/components/onboarding/GuidedTraining.vue';
import AppModal from '@/components/ui/AppModal.vue';
import AuthGate from '@/components/auth/AuthGate.vue';
import { authState, checkAuthRequired, isAuthed, logout } from '@/api/authClient';

const ui = useUiStore();
const db = useDbStore();
const authChecked = ref(false);
const trainingOpen = ref(false);
provide('trainingActive', trainingOpen);
let trainingTrigger;

function startTraining(event) {
  trainingTrigger = event.currentTarget;
  if (ui.modal) ui.closeModal();
  trainingOpen.value = true;
}

async function closeTraining() {
  trainingOpen.value = false;
  await nextTick();
  trainingTrigger?.focus({ preventScroll: true });
}
const pending = computed(() => ui.role === 'pending');

// при старте: восстанавливаем профиль из localStorage, затем узнаём у /health,
// требует ли сервер авторизацию; только после этого тянем CRM
onMounted(async () => {
  try {
    const stored = JSON.parse(localStorage.getItem('biotorf.auth.user') || 'null');
    if (stored) ui.applySession(stored);
  } catch { /* битый localStorage */ }
  await checkAuthRequired();
  authChecked.value = true;
  if (isAuthed() && !pending.value) db.pullCrmState();
});

function onSession() {
  // успешный вход/регистрация (в т.ч. pending): применяем сессию из authClient
  ui.applySession(authState.user);
  authChecked.value = true;
  if (isAuthed() && !pending.value) db.pullCrmState();
  // pending-сотрудник сразу видит модалку профиля, чтобы заполнить данные
  if (authState.user && authState.user.role === 'pending') {
    ui.openMyProfile();
  }
}

// 401 — сессия истекла или её отозвали. 403 сообщает об ограничении доступа.
function sessionExpired() {
  trainingOpen.value = false;
  logout(); ui.clearSession(); ui.closeModal(); authChecked.value = true;
}
onMounted(() => window.addEventListener('unhandledrejection', (ev) => {
  const m = String(ev.reason && ev.reason.message || ev.reason || '');
  if (ev.reason?.status === 401 || /API 401/.test(m)) sessionExpired();
}));

// навигация кнопкой «назад/вперёд» браузера тоже меняет раздел
function onHashChange() {
  const v = (location.hash || '').replace(/^#\/?/, '').split('?')[0];
  if (v && views[v] && ui.view !== v) {
    ui.view = v;
    ui.search = '';
    ui.filter = 'Все';
  }
}
onMounted(() => window.addEventListener('hashchange', onHashChange));
onBeforeUnmount(() => window.removeEventListener('hashchange', onHashChange));

const views = {
  automation: markRaw(defineAsyncComponent(() => import('@/views/AutomationView.vue'))),
  dashboard: markRaw(defineAsyncComponent(() => import('@/views/DashboardView.vue'))),
  registry: markRaw(defineAsyncComponent(() => import('@/views/RegistryView.vue'))),
  crm: markRaw(defineAsyncComponent(() => import('@/views/CrmView.vue'))),
  comms: markRaw(defineAsyncComponent(() => import('@/views/CommsView.vue'))),
  pipeline: markRaw(defineAsyncComponent(() => import('@/views/PipelineView.vue'))),
  pilots: markRaw(defineAsyncComponent(() => import('@/views/PilotsView.vue'))),
  knowledge: markRaw(defineAsyncComponent(() => import('@/views/KnowledgeView.vue'))),
  social: markRaw(defineAsyncComponent(() => import('@/views/SocialView.vue'))),
  products: markRaw(defineAsyncComponent(() => import('@/views/ProductsView.vue'))),
  orders: markRaw(defineAsyncComponent(() => import('@/views/OrdersView.vue'))),
  production: markRaw(defineAsyncComponent(() => import('@/views/ProductionView.vue'))),
  warehouse: markRaw(defineAsyncComponent(() => import('@/views/WarehouseView.vue'))),
  shipments: markRaw(defineAsyncComponent(() => import('@/views/ShipmentsView.vue'))),
  finance: markRaw(defineAsyncComponent(() => import('@/views/FinanceView.vue'))),
  tasks: markRaw(defineAsyncComponent(() => import('@/views/TasksView.vue'))),
  analytics: markRaw(defineAsyncComponent(() => import('@/views/AnalyticsView.vue'))),
  journey: markRaw(defineAsyncComponent(() => import('@/views/JourneyView.vue'))),
  calendar: markRaw(defineAsyncComponent(() => import('@/views/CalendarView.vue'))),
  media: markRaw(defineAsyncComponent(() => import('@/views/MediaView.vue'))),
  notifications: markRaw(defineAsyncComponent(() => import('@/views/NotificationsView.vue'))),
  employees: markRaw(defineAsyncComponent(() => import('@/views/EmployeesView.vue'))),
  organization: markRaw(defineAsyncComponent(() => import('@/views/OrganizationView.vue'))),
  channels: markRaw(defineAsyncComponent(() => import('@/views/ChannelsView.vue'))),
};

const currentView = computed(() => views[ui.view] || views.dashboard);
</script>

<template>
  <!-- пока сервер требует токен, а сессии нет — только экран входа/регистрации -->
  <AuthGate v-if="authChecked && authState.required && !isAuthed()" @session="onSession" />
  <div v-else-if="!authChecked" class="boot">Загрузка…</div>
  <main v-else-if="pending" class="pending">
    <section class="panel pending-box">
      <h1>Ожидается подтверждение доступа</h1>
      <p>Генеральный директор должен назначить вам рабочую роль. Пока можно заполнить свой профиль.</p>
      <button class="btn primary" @click="ui.openMyProfile()">Мой профиль</button>
      <button class="btn ghost" @click="sessionExpired">Выйти</button>
    </section>
    <AppModal />
  </main>
  <div v-else class="shell" :inert="trainingOpen">
    <AppSidebar />
    <main class="main">
      <AppTopbar @start-training="startTraining" />
      <div class="content">
        <Suspense>
          <component :is="currentView" />
          <template #fallback>
            <div class="empty">Загрузка раздела…</div>
          </template>

        </Suspense>
      </div>
    </main>
    <AppModal />
    <GuidedTraining v-if="trainingOpen" @close="closeTraining" />
  </div>
</template>

<style scoped>
.boot{min-height:100vh;display:grid;place-items:center;color:#729e8e;font-size:13px}
.pending{min-height:100vh;display:grid;place-items:center;padding:20px}
.pending-box{max-width:480px;padding:24px}
.pending-box .btn{margin-inline-end:8px}
</style>
