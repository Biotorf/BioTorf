const datePlus = (days) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

const hoursAgo = (h) => {
  const d = new Date();
  d.setHours(d.getHours() - h);
  return d.toISOString();
};

export const SAMPLE = {
  version: 1,
  mode: 'demo',
  users: [
    { id: 'u1', name: 'Директор (демо)', role: 'director' },
    { id: 'u2', name: 'РОП (демо)', role: 'sales_head' },
    { id: 'u3', name: 'Менеджер А (демо)', role: 'sales' },
    { id: 'u4', name: 'Агроном (демо)', role: 'agronomist' },
  ],
  farms: [
    { id: 'F-001', name: 'Демо • Хозяйство Чуй', type: 'КФХ', region: 'Чуйская область', crop: 'Картофель', area: 86, owner: 'Менеджер А', phone: '', source: 'Instagram', status: 'Активный', next: datePlus(2), note: 'Контроль пилота по картофелю' },
    // ... остальные 5 записей 1:1 из исходника
  ],
  leads: [
    { id: 'L-001', farmId: 'F-004', name: 'Запрос BIOTORF — фасоль', source: 'Мероприятие', status: 'Новый лид', owner: 'Менеджер Б', date: datePlus(-1), next: datePlus(0) },
    // ...
  ],
  stages: ['Новый лид', 'Связаться', 'Контакт установлен', 'Квалификация', 'Потенциальный клиент', 'Агрономическая диагностика', 'Предложен пилот', 'Пилот согласован', 'Пилот идет', 'Результат получен', 'Экономика рассчитана', 'КП отправлено', 'Переговоры', 'Счет/договор', 'Ожидается оплата', 'Оплачено', 'Отгружено', 'Получено клиентом', 'Сопровождение', 'Повторный заказ', 'Сезонный контракт'],
  deals: [ /* ... 6 записей 1:1 ... */ ],
  pilotStages: [ /* ... 18 стадий ... */ ],
  pilots: [ /* ... 4 записи ... */ ],
  applications: [ /* ... 3 записи ... */ ],
  knowledge: [ /* ... 8 статей ... */ ],
  social: [ /* ... 3 поста ... */ ],
  skus: [ /* ... 5 SKU ... */ ],
  cost: { paste_rub: 420, fx_kgs_rub: 1.0249, inbound_per_l_paste: 30, local_per_l_paste: 15, agro_mfg: 15, home_mfg: 25, fixed_month: 450000, scenario_volume: 5000, source: 'Калькуляция 07.10.2026 — допущения, не утвержденный прайс' },
  warehouse: [ /* ... 5 записей ... */ ],
  stockMoves: [],
  production: [ /* ... 2 записи ... */ ],
  orders: [ /* ... 3 записи ... */ ],
  shipments: [ /* ... 2 записи ... */ ],
  invoices: [ /* ... 3 записи ... */ ],
  payments: [],
  tasks: [ /* ... 5 записей ... */ ],
  // Единая лента коммуникаций: звонки (телефония) и сообщения (Telegram / WhatsApp).
  // kind: 'call' | 'telegram' | 'whatsapp'; dir: 'in' | 'out'
  comms: [
    { id: 'C-001', kind: 'call', dir: 'in', farmId: 'F-001', contact: 'Аскер (владелец)', phone: '+996 700 112 233', ts: hoursAgo(2), duration: 260, status: 'Разговор', note: 'Вопрос по обработке картофеля на следующей неделе', read: false },
    { id: 'C-002', kind: 'telegram', dir: 'in', farmId: 'F-001', contact: 'Аскер (владелец)', handle: '@asker_farmer', ts: hoursAgo(4), text: 'Добрый день! Когда можно привезти BIOTORF на пробу? Участок 40 га, картофель.', read: false },
    { id: 'C-003', kind: 'whatsapp', dir: 'out', farmId: 'F-002', contact: 'Розница «Ак-Биле»', phone: '+996 555 443 322', ts: hoursAgo(7), text: 'Отправляем прайс по фасовке 1 л и 5 л. Условия для розницы — в приложении.', read: true },
    { id: 'C-004', kind: 'call', dir: 'out', farmId: null, contact: null, phone: '+996 312 55 66 77', ts: hoursAgo(9), duration: 0, status: 'Пропущенный', note: 'Входящий с неизвестного номера был перезвонен — не дозвонились', read: true },
    { id: 'C-005', kind: 'telegram', dir: 'in', farmId: null, contact: null, handle: '@greenhouse_chui', ts: hoursAgo(26), text: 'Здравствуйте, интересует препарат для теплиц (огурец). Работаете с дилерами?', read: false },
    { id: 'C-006', kind: 'call', dir: 'in', farmId: 'F-003', contact: 'Николай Петрович', phone: '+996 770 887 665', ts: hoursAgo(30), duration: 145, status: 'Разговор', note: 'Обсудили сроки отгрузки, просит счёт до пятницы', read: true },
  ],
  audit: [],
  contacts: [],
  clientNotes: [],
  clientDocs: [],
  media: [],
  marketingAttributions: [],
  preferences: {},
};