import { defineStore } from 'pinia';
import { defineAsyncComponent, markRaw } from 'vue';

// ── hash-роутинг: активный раздел живёт в URL (#/comms), поэтому при
// обновлении страницы пользователь остаётся там же, а не сбрасывается в «Обзор»
const VALID_VIEWS = [
  'dashboard', 'automation', 'registry', 'crm', 'comms', 'pipeline', 'pilots', 'knowledge', 'social',
  'products', 'orders', 'production', 'warehouse', 'shipments', 'finance',
  'tasks', 'analytics', 'journey', 'calendar', 'media', 'notifications', 'employees', 'channels', 'organization',
];
function viewFromHash() {
  const v = (location.hash || '').replace(/^#\/?/, '').split('?')[0];
  return VALID_VIEWS.includes(v) ? v : null;
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    view: viewFromHash() || 'dashboard',
    // роль приходит с сервера (JWT) — больше не демо-переключатель
    role: localStorage.getItem('biotorf.auth.user')
      ? (JSON.parse(localStorage.getItem('biotorf.auth.user')).role || 'director')
      : 'director',
    login: '', name: '', demoRole: false,
    search: '',
    filter: 'Все',
    modal: null,           // { title, component, props }
    activeWork: null,      // { kind, id }
    calendarPrev: 'dashboard',
    calMode: 'Месяц',
    calAnchor: new Date(),
    socialTab: 'content',
    commsFilter: 'all',        // all | call | telegram | whatsapp
    commsFocusFarm: null,      // farmId, на котором сфокусироваться в ленте
  }),
  actions: {
    openClient(farmId) {
      this.closeModal();
      this.go('crm', { client: farmId });
    },
    openJourney(journeyId) {
      this.activeWork = { kind: 'journey', id: journeyId };
      this.go('journey', { id: journeyId });
    },
    openRecord(kind, id) {
      // единый просмотр/редактирование объекта из любого реестра (§5 руководства)
      this.openModal(`Редактор · ${kind}`, () => import('@/components/forms/RecordEditForm.vue'), { kind, id });
    },
    openLeadCard(leadId) {
      this.openModal('Лид и сквозной процесс', () => import('@/views/LeadJourneyModal.vue'), { leadId });
    },
    openComms(farmId = null) {
      if (farmId) this.commsFocusFarm = farmId;
      this.go('comms');
    },
    go(view, params) {
      this.view = view;
      this.search = '';
      this.filter = 'Все';
      const query = new URLSearchParams(params);
      const hash = '#/' + view + (query.size ? '?' + query : '');
      if (location.hash !== hash) location.hash = hash;
    },
    openModal(title, component, props = {}) {
      const view = typeof component === 'function' ? defineAsyncComponent(component) : component;
      this.modal = { title, component: markRaw(view), props };
    },
    closeModal() {
      this.modal = null;
      this.activeWork = null;
    },
    setRole(role) {
      this.role = role;
    },
    applySession(user) {
      // вызывается после входа/регистрации: роль только что созданного аккаунта
      this.login = user.login || user.user || '';
      this.name = user.name || '';
      this.role = user.role || 'director';
      localStorage.setItem('biotorf.auth.user', JSON.stringify(user));
    },
    clearSession() {
      this.login = ''; this.name = '';
      this.role = 'director';
    },
    logoutEverywhere() {
      // полный выход: очищаем хранилище и перезагружаем приложение —
      // App.vue по отсутствующему токену покажет экран входа (AuthGate)
      localStorage.removeItem('biotorf.auth.token');
      localStorage.removeItem('biotorf.auth.user');
      this.clearSession();
      location.reload();
    },
    openMyProfile() {
      // модалка профиля сотрудника — открывается из мини-профиля топбара
      this.openModal('Мой профиль', () => import('@/components/auth/ProfileModal.vue'), {});
    },
  },
});