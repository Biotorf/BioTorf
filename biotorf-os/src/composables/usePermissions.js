import { computed } from 'vue';
import { useUiStore } from '@/stores/ui';

const ROLES = {
  director: 'Генеральный директор',
  operations: 'Операционный руководитель',
  sales_head: 'Руководитель продаж',
  dispatcher: 'CRM-диспетчер',
  sales: 'Менеджер продаж',
  agronomist: 'Агроном',
  production: 'Производство',
  warehouse: 'Склад',
  logistics: 'Логистика',
  finance: 'Финансы',
  marketing: 'Маркетинг',
};

const EDIT_RULES = {
  crm: ['director', 'operations', 'sales_head', 'dispatcher', 'sales'],
  comms: ['director', 'operations', 'sales_head', 'dispatcher', 'sales', 'agronomist', 'marketing'],
  pipeline: ['director', 'sales_head', 'sales'],
  pilots: ['director', 'agronomist', 'sales_head'],
  knowledge: ['director', 'agronomist', 'sales_head', 'marketing'],
  social: ['director', 'marketing'],
  orders: ['director', 'operations', 'sales_head', 'sales', 'finance'],
  production: ['director', 'operations', 'production'],
  warehouse: ['director', 'operations', 'warehouse'],
  shipments: ['director', 'operations', 'logistics'],
  finance: ['director', 'finance'],
  tasks: Object.keys(ROLES),
};

const CRM_SPECIALTY_COLLECTIONS = {
  agronomist: ['pilots', 'applications', 'knowledge', 'media'],
  production: ['production'],
  warehouse: ['warehouse'],
  logistics: ['shipments'],
  finance: ['invoices', 'payments'],
  marketing: ['media', 'social', 'knowledge'],
};


export function usePermissions() {
  const ui = useUiStore();
  const canEdit = (section) => (EDIT_RULES[section] || []).includes(ui.role);
  const canEditCollection = (collection) => collection === 'logistics'
    ? canEdit('shipments')
    : canEdit('crm') || (collection === 'tasks' && canEdit('tasks')) ||
      (CRM_SPECIALTY_COLLECTIONS[ui.role] || []).includes(collection);
  const canApprove = () => ['director', 'agronomist'].includes(ui.role);
  const canSeeFarm = (farm) => ui.role !== 'sales' || [ui.login, ui.name, 'Менеджер А']
    .filter(Boolean).includes(farm.owner);
  return { ROLES, canEdit, canEditCollection, canApprove, canSeeFarm };
}