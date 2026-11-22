const SCHEMAS = {
  farms:      ['id', 'name', 'type', 'region', 'crop', 'area', 'owner', 'status', 'next', 'phone', 'notes'],
  leads:      ['id', 'name', 'contactName', 'phone', 'company', 'farmId', 'region', 'source', 'owner', 'status', 'next'],
  deals:      ['id', 'title', 'farmId', 'journeyId', 'stage', 'volumeL', 'amount', 'owner', 'next'],
  orders:     ['id', 'number', 'farmId', 'dealId', 'journeyId', 'quoteId', 'date', 'sku', 'product', 'qty', 'unit', 'items', 'amount', 'status', 'owner'],
  invoices:   ['id', 'number', 'orderId', 'dealId', 'farmId', 'journeyId', 'date', 'due', 'amount', 'paid', 'status'],
  payments:   ['id', 'invoiceId', 'orderId', 'date', 'amount', 'method', 'comment'],
  shipments:  ['id', 'number', 'orderId', 'farmId', 'journeyId', 'date', 'planDate', 'carrier', 'vehicle', 'transport', 'driver', 'plate', 'route', 'items', 'amount', 'status', 'received'],
  tasks:      ['id', 'title', 'owner', 'due', 'priority', 'status', 'refKind', 'refId'],
  contacts:   ['id', 'farmId', 'name', 'role', 'phone', 'email', 'primary'],
  skus:       ['id', 'name', 'line', 'pack', 'recipe', 'status', 'category', 'unit', 'price', 'stock', 'notes'],
  warehouse:  ['id', 'sku', 'batch', 'qty', 'reserved', 'unit', 'warehouse', 'expiry', 'status', 'orderId'],
  production: ['id', 'date', 'sku', 'product', 'lot', 'qty', 'unit', 'status', 'shift', 'operator', 'notes', 'orderId'],
  pilots:     ['id', 'title', 'farmId', 'dealId', 'journeyId', 'crop', 'area', 'startDate', 'endDate', 'nextCheck', 'status', 'owner', 'result'],
  quotes:     ['id', 'number', 'dealId', 'farmId', 'journeyId', 'date', 'items', 'terms', 'total', 'status'],
  journeys:   ['id', 'leadId', 'farmId', 'dealId', 'pilotId', 'quoteId', 'orderId', 'invoiceId', 'shipmentId', 'stage', 'owner', 'next', 'qualification', 'history'],
  knowledge:  ['id', 'title', 'category', 'tags', 'text'],
  media:      ['id', 'title', 'kind', 'url', 'tag', 'date', 'pilotId', 'farmId', 'consent', 'note'],
  clientNotes: ['id', 'farmId', 'ts', 'text'],
  applications: ['id', 'pilotId', 'farmId', 'date', 'dose', 'method', 'notes'],
  clientDocs: ['id', 'farmId', 'title', 'type', 'date', 'url', 'notes'],
  logistics: ['id', 'kind', 'number', 'date', 'status', 'party', 'farmId', 'orderId', 'warehouse', 'vehicle', 'driver', 'base', 'note', 'items', 'act'],
  social:     ['id', 'platform', 'title', 'status', 'scheduledDate', 'link'],
};

export const COLL_RU = {
  farms: 'Хозяйства', leads: 'Лиды', deals: 'Сделки', orders: 'Заказы',
  invoices: 'Счета', payments: 'Платежи', shipments: 'Отгрузки', tasks: 'Задачи',
  contacts: 'Контакты', skus: 'Товары (SKU)', warehouse: 'Склад', production: 'Производство',
  pilots: 'Пилоты', quotes: 'КП', journeys: 'Маршруты клиентов', knowledge: 'База знаний',
  clientNotes: 'Заметки клиентов', applications: 'Обработки', clientDocs: 'Документы клиентов',
  logistics: 'Поставки и выгрузки',
  media: 'Медиа', social: 'Соцсети',
};

export const FIELD_RU = {
  id: 'ID', name: 'Название', contactName: 'Контактное лицо', phone: 'Телефон',
  company: 'Компания', region: 'Регион', source: 'Источник', owner: 'Ответственный',
  status: 'Статус', next: 'Следующее действие', notes: 'Заметки', type: 'Тип',
  crop: 'Культура', area: 'Площадь', title: 'Название / тема', farmId: 'Хозяйство (ID)',
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
  scheduledDate: 'Дата публикации', link: 'Ссылка',
};

export const REF_FIELD = { farmId: 'farms', dealId: 'deals', orderId: 'orders', invoiceId: 'invoices', leadId: 'leads', pilotId: 'pilots', sku: 'skus', skuId: 'skus', journeyId: 'journeys', quoteId: 'quotes', shipmentId: 'shipments' };

const legacyFields = {
  orders: { number: 'num' },
  warehouse: { warehouse: 'location' },
  production: { lot: 'batch' },
  pilots: { nextCheck: 'next' },
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
  return record?.[key] ?? record?.[legacyFields[coll]?.[key]];
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
