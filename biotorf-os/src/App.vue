<script setup>
import { computed, defineAsyncComponent, markRaw } from 'vue';
import { useUiStore } from '@/stores/ui';
import AppSidebar from '@/components/layout/AppSidebar.vue';
import AppTopbar from '@/components/layout/AppTopbar.vue';
import AppModal from '@/components/ui/AppModal.vue';

const ui = useUiStore();

const views = {
  dashboard: markRaw(defineAsyncComponent(() => import('@/views/DashboardView.vue'))),
  crm: markRaw(defineAsyncComponent(() => import('@/views/CrmView.vue'))),
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
};

const currentView = computed(() => views[ui.view] || views.dashboard);
</script>

<template>
  <div class="shell">
    <AppSidebar />
    <main class="main">
      <AppTopbar />
      <div class="content">
        <Suspense>
          <component :is="currentView" />
          <template #fallback>
            <div class="empty">Загрузка раздела…</div>
          </template>
        </Suspense>
        <footer class="app-footer">
          BIOTORF Business OS · Vue 3 · демонстрационные показатели
        </footer>
      </div>
    </main>
    <AppModal />
  </div>
</template>