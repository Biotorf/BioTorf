import { REQUISITE_FIELDS } from './requisites';

const SCHEMAS = {
  farms:      ['id', 'name', 'type', 'region', 'crop', 'area', 'owner', 'status', 'next', 'phone', 'email', ...REQUISITE_FIELDS.map(([key]) => key), 'source', 'notes'],
  leads:      ['id', 'name', 'contactName', 'phone', 'company', 'farmId', 'region', 'source', 'owner', 'status', 'next'],
  deals:      ['id', 'title', 'farmId', 'journeyId', 'stage', 'volumeL', 'amount', 'owner', 'next'],
  orders:     ['id', 'number', 'farmId', 'dealId', 'journeyId', 'quoteId', 'date', 'sku', 'product', 'qty', 'unit', 'items', 'amount', 'status', 'owner'],
  invoices:   ['id', 'number', 'orderId', 'dealId', 'farmId', 'journeyId', 'date', 'due', 'amount', 'paid', 'status'],
  payments:   ['id', 'invoiceId', 'orderId', 'date', 'amount', 'method', 'comment'],
  shipments:  ['id', 'number', 'orderId', 'farmId', 'journeyId', 'date', 'planDate', 'carrier', 'vehicle', 'transport', 'driver', 'plate', 'route', 'items', 'amount', 'status', 'received'],
  tasks:      ['id', 'title', 'owner', 'due', 'priority', 'status', 'refKind', 'refId'],
  contacts:   ['id', 'farmId', 'name', 'role', 'phone', 'whatsapp', 'telegram', 'email', 'primary'],
  skus:       ['id', 'name', 'line', 'pack', 'recipe', 'recipeVersion', 'pasteKgPerL', 'powderKgPerL', 'lossPct', 'status', 'category', 'unit', 'price', 'stock', 'notes'],
  warehouse:  ['id', 'sku', 'batch', 'qty', 'reserved', 'unit', 'warehouse', 'expiry', 'status', 'orderId'],
  production: ['id', 'date', 'sku', 'product', 'lot', 'qty', 'unit', 'plannedVolumeL', 'recipeVersion', 'plannedPasteKg', 'plannedPowderKg', 'status', 'supplyId', 'inputLot', 'pasteUsedKg', 'powderUsedKg', 'actualQty', 'qcStatus', 'shift', 'operator', 'notes', 'orderId'],
  pilots:     ['id', 'title', 'farmId', 'dealId', 'journeyId', 'crop', 'area', 'startDate', 'endDate', 'nextCheck', 'control', 'goal', 'status', 'owner', 'result'],
  quotes:     ['id', 'number', 'dealId', 'farmId', 'journeyId', 'date', 'items', 'terms', 'total', 'status'],
  journeys:   ['id', 'leadId', 'farmId', 'dealId', 'pilotId', 'quoteId', 'orderId', 'invoiceId', 'shipmentId', 'stage', 'owner', 'next', 'qualification', 'history'],
  knowledge:  ['id', 'title', 'category', 'crop', 'version', 'owner', 'status', 'public', 'source', 'tags', 'text'],
  media:      ['id', 'title', 'kind', 'url', 'tag', 'date', 'pilotId', 'farmId', 'consent', 'note'],
  clientNotes: ['id', 'farmId', 'ts', 'text'],
  applications: ['id', 'pilotId', 'farmId', 'date', 'dose', 'method', 'notes'],
  clientDocs: ['id', 'farmId', 'title', 'type', 'date', 'url', 'notes'],
  logistics: ['id', 'kind', 'number', 'date', 'status', 'party', 'farmId', 'orderId', 'warehouse', 'vehicle', 'driver', 'base', 'note', 'items', 'act'],
  social:     ['id', 'platform', 'title', 'kind', 'pilotId', 'caption', 'consent', 'caseApproved', 'owner', 'status', 'scheduledDate', 'link'],
};

export const COLL_RU = {
  farms: 'Клиенты', leads: 'Лиды', deals: 'Сделки', orders: 'Заказы',
  invoices: 'Счета', payments: 'Платежи', shipments: 'Отгрузки', tasks: 'Задачи',
  contacts: 'Контакты', skus: 'Товары (SKU)', warehouse: 'Склад', production: 'Производство',
  pilots: 'Пилоты', quotes: 'КП', journeys: 'Маршруты клиентов', knowledge: 'База знаний',
  clientNotes: 'Заметки клиентов', applications: 'Обработки', clientDocs: 'Документы клиентов',
  logistics: 'Поставки и выгрузки',
  media: 'Медиа', social: 'Соцсети',
};

export const FIELD_RU = {
  ...Object.fromEntries(REQUISITE_FIELDS),
  id: 'ID', name: 'Название', contactName: 'Контактное лицо', phone: 'Телефон',
  company: 'Компания', region: 'Регион', source: 'Источник', owner: 'Ответственный',
  status: 'Статус', next: 'Следующее действие', notes: 'Заметки', type: 'Тип',
  crop: 'Культура', area: 'Площадь', title: 'Название / тема', farmId: 'Клиент',
  stage: 'Этап', volumeL: 'Объём, л', amount: 'Сумма', number: 'Номер', dealId: 'Сделка (ID)',
  date: 'Дата', orderId: 'Заказ (ID)', invoiceId: 'Счёт (ID)', paid: 'Оплачен (да/нет)',
  method: 'Способ оплаты', comment: 'Комментарий', transport: 'Транспорт', driver: 'Водитель',
  plate: 'Гос. номер', route: 'Маршрут', due: 'Срок', priority: 'Приоритет',
  refKind: 'Связь · тип', refId: 'Связь · ID', role: 'Должность', email: 'E-mail',
  primary: 'Основной контакт', sku: 'Артикул (SKU)', category: 'Категория', unit: 'Ед. изм.',
  price: 'Цена', stock: 'Остаток', batch: 'Партия', qty: 'Количество', location: 'Локация',
  expiry: 'Срок годности', product: 'Продукт', shift: 'Смена', operator: 'Оператор',
  startDate: 'Начало', endDate: 'Окончание', result: 'Результат', leadId: 'Лид (ID)',
  tags: 'Теги', text: 'Текст', url: 'Ссылка', tag: 'Метка', platform: 'Платформа',
  line: 'Линейка', pack: 'Фасовка, л', recipe: 'Рецептура', reserved: 'Резерв', warehouse: 'Склад',
  lot: 'Номер лота', nextCheck: 'Следующий контроль', pilotId: 'Пилот',
  kind: 'Вид записи', consent: 'Согласие на публикацию', note: 'Примечание',
  journeyId: 'Маршрут клиента', quoteId: 'КП', shipmentId: 'Отгрузка',
  items: 'Позиции', terms: 'Условия', total: 'Итого', planDate: 'Плановая дата',
  carrier: 'Перевозчик', vehicle: 'Автомобиль', received: 'Получено',
  ts: 'Дата и время', dose: 'Дозировка', qualification: 'Квалификация', history: 'История',
  party: 'Контрагент', base: 'Основание', act: 'Акт', createdAt: 'Создано',
  caption: 'Текст публикации', caseApproved: 'Кейс утверждён', public: 'Публичный материал', version: 'Версия',
  packs: 'Количество', skuId: 'Артикул (SKU)', sum: 'Сумма', liters: 'Объём, л',
  scheduledDate: 'Дата публикации', link: 'Ссылка', whatsapp: 'WhatsApp', telegram: 'Telegram',
  plannedVolumeL: 'План выпуска, л', supplyId: 'Поставка сырья', inputLot: 'Партия сырья',
  actualQty: 'Фактический выпуск', qcStatus: 'Контроль качества', pasteUsedKg: 'Расход пасты, кг', powderUsedKg: 'Расход порошка, кг',
  recipeVersion: 'Версия рецептуры', pasteKgPerL: 'Паста на 1 л, кг', powderKgPerL: 'Порошок на 1 л, кг (прежняя норма)',
  lossPct: 'Плановые потери сырья, %', plannedPasteKg: 'План расхода пасты, кг', plannedPowderKg: 'План расхода порошка, кг',
  material: 'Тип сырья', control: 'Контрольный участок', goal: 'Цель пилота',
};

export const REF_FIELD = { farmId: 'farms', dealId: 'deals', orderId: 'orders', invoiceId: 'invoices', leadId: 'leads', pilotId: 'pilots', sku: 'skus', skuId: 'skus', journeyId: 'journeys', quoteId: 'quotes', shipmentId: 'shipments', supplyId: 'logistics' };

const dictionaryFields = {
  region: 'regions', crop: 'crops', source: 'sources', owner: 'owners',
  unit: 'unitPack', location: 'locations', warehouse: 'locations',
  transport: 'transport', vehicle: 'transport', driver: 'drivers', plate: 'plates', carrier: 'carriers',
  shift: 'shifts', operator: 'operators', platform: 'platforms',
  product: 'products', priority: 'priorities', method: 'methods', category: 'categories',
};

export function crmDictionaryKey(coll, field) {
  if (coll === 'farms' && field === 'status') return 'statuses';
  if (coll === 'farms' && field === 'type') return 'types';
  if (coll === 'clientDocs' && field === 'type') return 'documentTypes';
  if (coll === 'skus' && field === 'line') return 'lines';
  if (coll === 'applications' && field === 'method') return 'applicationMethods';
  return Object.hasOwn(dictionaryFields, field) ? dictionaryFields[field] : undefined;
}

const legacyFields = {
  farms: { notes: 'note' },
  orders: { number: 'num' },
  warehouse: { warehouse: 'location' },
  production: { lot: 'batch' },
  pilots: { nextCheck: 'next', startDate: 'date' },
  knowledge: { text: 'summary' },
  social: { platform: 'channel', scheduledDate: 'date', link: 'publicUrl' },
  media: { kind: 'type', date: 'uploadedAt', note: 'notes' },
};
export const REF_KINDS = {
  deal: 'deals', lead: 'leads', farm: 'farms', order: 'orders', invoice: 'invoices',
  shipment: 'shipments', pilot: 'pilots', journey: 'journeys', quote: 'quotes', task: 'tasks',
};

export function crmFields(coll, records) {
  const keys = new Set(SCHEMAS[coll] || ['id']);
  for (const record of records) Object.keys(record).forEach((key) => keys.add(key));
  const aliases = Object.values(legacyFields[coll] || {});
  return [...keys].filter((key) => !key.startsWith('_') && !aliases.includes(key));
}

export function crmValue(coll, record, key) {
  const value = record?.[key] ?? record?.[legacyFields[coll]?.[key]];
  return coll === 'deals' && key === 'stage' ? dealStage(value) : value;
}

export function crmTitle(record) {
  return record.name || record.title || record.number || record.num || record.id;
}

export function crmReferences(coll, record) {
  const refs = Object.entries(REF_FIELD).map(([field, target]) => ({ field, coll: target, id: record[field] }));
  if (REF_KINDS[record.refKind]) refs.push({ field: 'refId', coll: REF_KINDS[record.refKind], id: record.refId });
  for (const item of Array.isArray(record.items) ? record.items : []) {
    if (item) refs.push({ field: 'items', coll: 'skus', id: item.sku || item.skuId });
  }
  return refs.filter((link) => link.id && (link.coll !== coll || link.id !== record.id));
}

export function crmFieldLabel(coll, key) {
  if (coll === 'farms' && key === 'name') return 'Имя или название';
  if (coll === 'farms' && key === 'type') return 'Тип клиента';
  if (coll === 'clientDocs' && key === 'type') return 'Тип документа';
  if (coll === 'applications' && key === 'method') return 'Способ обработки';
  if (coll === 'logistics' && key === 'kind') return 'Тип документа';
  if (coll === 'logistics' && key === 'vehicle') return 'Транспорт';
  if (coll === 'logistics' && key === 'lot') return 'Партия поставщика';
  return FIELD_RU[key] || key;
}

export const LOGISTICS_KINDS = { supply: 'Поставка (приход)', dispatch: 'Выгрузка / отгрузка' };

export const DEAL_STAGES = [
  'Новая', 'Квалификация', 'Пилот или КП', 'КП отправлено', 'Переговоры',
  'Счёт выставлен', 'Оплачено', 'Доставка', 'Получено клиентом', 'Завершена',
];
const dealStageAliases = new Map([
  ['Пилот идет', 'Пилот или КП'], ['Пилот идёт', 'Пилот или КП'], ['Пилот согласован', 'Пилот или КП'],
  ['Счет/договор', 'Счёт выставлен'], ['Отгружено', 'Доставка'],
]);
export function dealStage(value) { return dealStageAliases.get(value) || value; }

const statuses = {
  farms: ['Потенциальный', 'Активный', 'Неактивный'],
  leads: ['Новый лид', 'Связаться', 'Контакт установлен', 'В работе', 'Квалифицирован', 'Сделка создана', 'Отказ'],
  orders: ['Новый', 'Подтверждён', 'В производство', 'Готов к отгрузке', 'Оплачен', 'Отгружен', 'Отменён'],
  invoices: ['Выставлен', 'Оплачен', 'Просрочен'],
  shipments: ['Запланирована', 'В пути', 'Доставлена', 'Получено клиентом'],
  warehouse: ['В наличии', 'Зарезервировано', 'Списан'],
  production: ['План', 'В работе', 'Завершено'],
  tasks: ['Открыта', 'В работе', 'Выполнена', 'Отменена'],
  quotes: ['Черновик', 'Отправлено', 'Принят', 'Отклонено'],
  social: ['Идея', 'Черновик', 'В работе', 'На согласовании', 'Готово к публикации', 'Запланировано', 'Опубликовано'],
  knowledge: ['Черновик', 'На проверке', 'Утверждено'],
  skus: ['В модели', 'Активный', 'Архив'],
};

export function statusOptions(coll, records, additional = []) {
  return [...new Set([...(statuses[coll] || []), ...additional, ...records.map((row) => row.status)]
    .filter((value) => typeof value === 'string' && value.trim()))];
}

export function crmDisplayValue(value) {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}
