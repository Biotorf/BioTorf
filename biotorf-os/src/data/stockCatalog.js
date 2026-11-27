export const RAW_WAREHOUSE = 'Склад сырья';
export const FINISHED_WAREHOUSE = 'Склад готовой продукции';
export const PASTE = { id: 'PASTE', name: 'Паста-концентрат', stockType: 'raw', unit: 'кг' };
export const stockTypes = { raw: 'Сырьё', packaging: 'Тара и упаковка', finished: 'Готовая продукция' };
export const isFinished = (product) => !product.stockType || product.stockType === 'finished';
export const stockUnit = (product) => product?.stockType === 'raw' ? 'кг' : 'шт.';
