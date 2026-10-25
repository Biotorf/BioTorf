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
  version: 3,          // v3: сквозной процесс (journeys/quotes) по руководству v0.9
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
  // Единая лента коммуникаций живёт на бэкенде (backend/, API /api/comms).
  // Тестовые сообщения из демо-версии удалены — пустая стартовая лента.
  comms: [],
  audit: [],
  contacts: [],
  clientNotes: [],
  clientDocs: [],
  media: [],
  marketingAttributions: [],
  preferences: {},
  // ── Сквозной процесс (руководство v0.9, раздел 3) ─────────────
  // journey = единая карточка маршрута: лид → квалификация → сделка →
  // пилот (опц.) → КП → заказ → счёт → оплата → доставка → сопровождение.
  journeys: [
    {
      id: 'J-001', leadId: 'L-001', farmId: null, dealId: null, pilotId: null, quoteId: null, orderId: null, invoiceId: null,
      stage: 'Квалификация', owner: 'Менеджер Б', next: datePlus(1), createdAt: datePlus(-2),
      qualification: null, history: [{ ts: hoursAgo(48), text: 'Маршрут создан из лида «Запрос BIOTORF — фасоль»' }],
    },
  ],
  quotes: [],
  clientDocs: [],
};