<script setup>
import { computed, ref, defineAsyncComponent, markRaw, onMounted, onBeforeUnmount } from 'vue';
import { useUiStore } from '@/stores/ui';
import { useDbStore } from '@/stores/db';
import AppSidebar from '@/components/layout/AppSidebar.vue';
import AppTopbar from '@/components/layout/AppTopbar.vue';
import AppModal from '@/components/ui/AppModal.vue';
import AuthGate from '@/components/auth/AuthGate.vue';
import { authState, checkAuthRequired, isAuthed, logout } from '@/api/authClient';

const ui = useUiStore();
const db = useDbStore();
const authChecked = ref(false);

// при старте: восстанавливаем профиль из localStorage, затем узнаём у /health,
// требует ли сервер авторизацию; только после этого тянем CRM
onMounted(async () => {
  try {
    const stored = JSON.parse(localStorage.getItem('biotorf.auth.user') || 'null');
    if (stored) ui.applySession(stored);
  } catch { /* битый localStorage */ }
  await checkAuthRequired();
  authChecked.value = true;
  if (isAuthed()) db.pullCrmState();
});

function onSession() {
  // успешный вход/регистрация (в т.ч. pending): применяем сессию из authClient
  ui.applySession(authState.user);
  authChecked.value = true;
  if (isAuthed()) db.pullCrmState();
  // pending-сотрудник сразу видит модалку профиля, чтобы заполнить данные
  if (authState.user && authState.user.role === 'pending') {
    ui.openModal('Мой профиль', () => import('@/components/auth/ProfileModal.vue'), {});
  }
}

// 401 — токен истёк/отозван, 403 — роль снята директором: выходим на экран входа
function sessionExpired() {
  logout(); ui.clearSession(); authChecked.value = true;
}
onMounted(() => window.addEventListener('unhandledrejection', (ev) => {
  const m = String(ev.reason && ev.reason.message || ev.reason || '');
  if (/API 401|API 403/.test(m)) sessionExpired();
}));

// навигация кнопкой «назад/вперёд» браузера тоже меняет раздел
function onHashChange() {
  const v = (location.hash || '').replace(/^#\/?/, '');
  if (v && views[v]) ui.view = v;
}
onMounted(() => window.addEventListener('hashchange', onHashChange));
onBeforeUnmount(() => window.removeEventListener('hashchange', onHashChange));

const views = {
  dashboard: markRaw(defineAsyncComponent(() => import('@/views/DashboardView.vue'))),
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
  channels: markRaw(defineAsyncComponent(() => import('@/views/ChannelsView.vue'))),
};

const currentView = computed(() => views[ui.view] || views.dashboard);
</script>

<template>
  <!-- пока сервер требует токен, а сессии нет — только экран входа/регистрации -->
  <AuthGate v-if="authChecked && authState.required && !isAuthed()" @session="onSession" />
  <div v-else-if="!authChecked" class="boot">Загрузка…</div>
  <div v-else class="shell">
    <AppSidebar />
    <main class="main">
      <AppTopbar />
      <div class="content">
        <Suspense>
          <component :is="currentView" />
          <template #fallback>
            <div class="empty">Загрузка раздела…</div>
          </template>

<style scoped>
.boot{min-height:100vh;display:grid;place-items:center;color:#729e8e;font-size:13px}
</style>
        </Suspense>
        <footer class="app-footer">
          BIOTORF Business OS · рабочая система
        </footer>
      </div>
    </main>
    <AppModal />
  </div>
</template>