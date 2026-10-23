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

export function usePermissions() {
  const ui = useUiStore();
  const canEdit = (section) => (EDIT_RULES[section] || []).includes(ui.role);
  const canApprove = () => ['director', 'agronomist'].includes(ui.role);
  const canSeeFarm = (farm) =>
    ui.role === 'sales' ? farm.owner === 'Менеджер А' : true;
  return { ROLES, canEdit, canApprove, canSeeFarm };
}