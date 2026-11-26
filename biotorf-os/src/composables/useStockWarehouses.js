import { computed, onMounted, ref, toValue } from 'vue';
import { stock } from '@/api/stockClient';

const legacyPrefix = 'legacy:';
const normalize = (name) => String(name || '').trim().toLocaleLowerCase('ru');

export function useStockWarehouses(records = []) {
  const warehouses = ref([]);
  const warehouseFilter = ref('');
  onMounted(async () => {
    try { warehouses.value = await stock('/stock/catalog/warehouses'); }
    catch { /* На старом API доступны названия складов из документов. */ }
  });

  function warehouseKey(row) {
    if (row?.warehouseId) return row.warehouseId;
    const name = normalize(row?.warehouse || row?.location);
    if (!name) return 'unassigned';
    return warehouses.value.find((warehouse) => normalize(warehouse.name) === name)?.id || legacyPrefix + name;
  }

  const warehouseOptions = computed(() => {
    const options = new Map(warehouses.value.map(({ id, name }) => [id, name]));
    options.set('unassigned', 'Склад не указан');
    for (const row of toValue(records)) {
      const key = warehouseKey(row);
      if (!options.has(key)) options.set(key, row.warehouse || row.location || 'Склад ' + key);
    }
    return [...options].map(([value, label]) => ({ value, label }));
  });

  function matchesWarehouse(row) {
    return !warehouseFilter.value || warehouseKey(row) === warehouseFilter.value;
  }

  return { warehouses, warehouseFilter, warehouseOptions, matchesWarehouse };
}
