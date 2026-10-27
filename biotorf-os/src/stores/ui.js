import { defineStore } from 'pinia';

// ── hash-роутинг: активный раздел живёт в URL (#/comms), поэтому при
// обновлении страницы пользователь остаётся там же, а не сбрасывается в «Обзор»
const VALID_VIEWS = [
  'dashboard', 'crm', 'comms', 'pipeline', 'pilots', 'knowledge', 'social',
  'products', 'orders', 'production', 'warehouse', 'shipments', 'finance',
  'tasks', 'analytics', 'journey', 'calendar', 'media', 'notifications', 'employees',
];
function viewFromHash() {
  const v = (location.hash || '').replace(/^#\/?/, '');
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
      this.openModal('Карточка клиента', () => import('@/views/ClientCardModal.vue'), { farmId });
    },
    openJourney(journeyId) {
      this.activeWork = { kind: 'journey', id: journeyId };
      this.go('journey');
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
    go(view) {
      this.view = view;
      this.search = '';
      this.filter = 'Все';
      // синхронизируем URL, чтобы F5 возвращал в тот же раздел
      const h = '#/' + view;
      if (location.hash !== h) history.replaceState(null, '', h);
    },
    openModal(title, component, props = {}) {
      this.modal = { title, component, props };
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