import { CLIENT_TYPES } from './clientDesk.js';

export const KYRGYZSTAN_REGIONS = [
  'Баткенская область', 'Джалал-Абадская область', 'Иссык-Кульская область',
  'Нарынская область', 'Ошская область', 'Таласская область', 'Чуйская область',
  'Бишкек', 'Ош',
];

export const OLD_REGION_PRESETS = [
  'Краснодарский край', 'Ростовская область', 'Ставропольский край', 'Алтайский край',
];

export const DEFAULT_LISTS = {
  regions: KYRGYZSTAN_REGIONS,
  crops: ['пшеница озимая', 'кукуруза', 'подсолнечник', 'соя', 'сахарная свёкла'],
  sources: ['WhatsApp', 'Telegram', 'Телефон', 'Сайт', 'Рекомендация', 'Выставка', 'Холодный звонок'],
  owners: [], statuses: ['активное'], types: [...CLIENT_TYPES, 'агрохолдинг', 'КФХ', 'ИП'],
  unitPack: ['5 л', '10 л', '200 мл', '1 л'],
  locations: ['склад А', 'склад Б'],
  transport: [], drivers: [], carriers: [], plates: [], shifts: [], operators: [], platforms: [],
  products: [], priorities: [], methods: [], applicationMethods: [], categories: [], suppliers: [],
  lines: ['AGRO', 'HOME'], documentTypes: [],
};

export const DICTIONARY_FIELDS = {
  regions: [['farms', 'region'], ['leads', 'region']],
  crops: [['farms', 'crop'], ['pilots', 'crop'], ['knowledge', 'crop']],
  sources: [['farms', 'source'], ['leads', 'source']],
  owners: [
    ['farms', 'owner'], ['leads', 'owner'], ['tasks', 'owner'], ['deals', 'owner'],
    ['orders', 'owner'], ['knowledge', 'owner'], ['journeys', 'owner'], ['pilots', 'owner'],
  ],
  locations: [['warehouse', 'warehouse'], ['warehouse', 'location'], ['logistics', 'warehouse']],
  transport: [['shipments', 'transport'], ['shipments', 'vehicle'], ['logistics', 'vehicle']],
  drivers: [['shipments', 'driver'], ['logistics', 'driver']],
  carriers: [['shipments', 'carrier']],
  products: [['orders', 'product'], ['production', 'product'], ['skus', 'name']],
  categories: [['skus', 'category'], ['knowledge', 'category']],
  suppliers: [['logistics', 'party']],
  lines: [['skus', 'line']],
  documentTypes: [['clientDocs', 'type']],
};

export function dictionaryKey(value) {
  return value.trim().toLowerCase();
}

export function mergeDictionaryValues(...groups) {
  const values = new Map();
  for (const group of groups) {
    for (const value of Array.isArray(group) ? group : []) {
      if (typeof value !== 'string' || !value.trim()) continue;
      const key = dictionaryKey(value);
      if (!values.has(key)) values.set(key, value.trim());
    }
  }
  return [...values.values()];
}

export function defaultDictionaries(saved = {}) {
  const values = {};
  for (const key of new Set([...Object.keys(DEFAULT_LISTS), ...Object.keys(saved || {})])) {
    values[key] = mergeDictionaryValues(DEFAULT_LISTS[key], saved?.[key]);
  }
  return values;
}
