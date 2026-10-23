import { defineStore } from 'pinia';

export const useUiStore = defineStore('ui', {
  state: () => ({
    view: 'dashboard',
    role: 'director',
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
    openComms(farmId = null) {
      if (farmId) this.commsFocusFarm = farmId;
      this.go('comms');
    },
    go(view) {
      this.view = view;
      this.search = '';
      this.filter = 'Все';
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
  },
});