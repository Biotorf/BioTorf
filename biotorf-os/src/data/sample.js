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
    { id: 'u1', name: 'Директор', role: 'director' },
    { id: 'u2', name: 'РОП', role: 'sales_head' },
    { id: 'u3', name: 'Менеджер А', role: 'sales' },
    { id: 'u4', name: 'Агроном', role: 'agronomist' },
  ],
  farms: [
    { id: 'F-001', name: 'Хозяйство Чуй', type: 'КФХ', region: 'Чуйская область', crop: 'Картофель', area: 86, owner: 'Менеджер А', phone: '', source: 'Instagram', status: 'Активный', next: datePlus(2), note: 'Контроль пилота по картофелю' },
    { id: 'F-002', name: 'Теплица Восток', type: 'Теплица', region: 'Ошская область', crop: 'Томат', area: 12, owner: 'Менеджер А', phone: '', source: 'WhatsApp', status: 'Потенциальный', next: datePlus(1), note: 'Подобрать схему применения' },
    { id: 'F-003', name: 'Сад Иссык-Куль', type: 'Сад', region: 'Иссык-Кульская область', crop: 'Яблоня', area: 31, owner: 'Менеджер Б', phone: '', source: 'Рекомендация', status: 'Активный', next: datePlus(-1), note: 'Запросить отзыв по применению' },
    { id: 'F-004', name: 'Фермер Талас', type: 'КФХ', region: 'Таласская область', crop: 'Фасоль', area: 54, owner: 'Менеджер Б', phone: '', source: 'Мероприятие', status: 'Новый', next: datePlus(4), note: 'Первичная встреча' },
    { id: 'F-005', name: 'Теплица Юг', type: 'Теплица', region: 'Джалал-Абадская область', crop: 'Огурец', area: 8, owner: 'Менеджер А', phone: '', source: 'Instagram', status: 'Активный', next: datePlus(3), note: 'Коммерческое предложение' },
    { id: 'F-006', name: 'Ягодное хозяйство', type: 'КФХ', region: 'Чуйская область', crop: 'Малина', area: 22, owner: 'Менеджер А', phone: '', source: 'WhatsApp', status: 'Испытание', next: datePlus(0), note: 'Получить фото после обработки' },
  ],
  leads: [
    { id: 'L-001', farmId: 'F-004', name: 'Запрос BIOTORF — фасоль', source: 'Мероприятие', status: 'Новый лид', owner: 'Менеджер Б', date: datePlus(-1), next: datePlus(0) },
    { id: 'L-002', farmId: 'F-002', name: 'Консультация по томатам', source: 'WhatsApp', status: 'Квалификация', owner: 'Менеджер А', date: datePlus(-2), next: datePlus(1) },
    { id: 'L-003', farmId: 'F-006', name: 'Пилот по малине', source: 'Instagram', status: 'Контакт установлен', owner: 'Менеджер А', date: datePlus(-7), next: datePlus(2) },
  ],
  stages: ['Новый лид', 'Связаться', 'Контакт установлен', 'Квалификация', 'Потенциальный клиент', 'Агрономическая диагностика', 'Предложен пилот', 'Пилот согласован', 'Пилот идет', 'Результат получен', 'Экономика рассчитана', 'КП отправлено', 'Переговоры', 'Счет/договор', 'Ожидается оплата', 'Оплачено', 'Отгружено', 'Получено клиентом', 'Сопровождение', 'Повторный заказ', 'Сезонный контракт'],
  deals: [
    { id: 'D-101', farmId: 'F-001', title: 'Сезонный контракт • картофель', amount: 380000, liters: 750, stage: 'Переговоры', owner: 'Менеджер А', next: datePlus(1), prob: 65 },
    { id: 'D-102', farmId: 'F-002', title: 'Томат • пилотная поставка', amount: 92000, liters: 140, stage: 'Пилот согласован', owner: 'Менеджер А', next: datePlus(2), prob: 35 },
    { id: 'D-103', farmId: 'F-003', title: 'Поставка для сада', amount: 240000, liters: 460, stage: 'КП отправлено', owner: 'Менеджер Б', next: datePlus(-1), prob: 50 },
    { id: 'D-104', farmId: 'F-005', title: 'Теплица • осенний цикл', amount: 165000, liters: 240, stage: 'Счет/договор', owner: 'Менеджер А', next: datePlus(0), prob: 75 },
    { id: 'D-105', farmId: 'F-006', title: 'Малина • расширенный пилот', amount: 54000, liters: 80, stage: 'Пилот идет', owner: 'Менеджер А', next: datePlus(3), prob: 25 },
    { id: 'D-106', farmId: 'F-004', title: 'Фасоль • первый контакт', amount: 128000, liters: 200, stage: 'Квалификация', owner: 'Менеджер Б', next: datePlus(4), prob: 15 },
  ],
  pilotStages: ['Новый пилот', 'Квалификация', 'Ожидается согласование', 'BIOTORF зарезервирован', 'BIOTORF отправлен', 'BIOTORF получен', 'Ожидается первая обработка', 'Испытание идет', 'Ожидается промежуточный контроль', 'Ожидается итоговый результат', 'Результат получен', 'Экономика рассчитана', 'Пилот успешен', 'Пилот без подтвержденного эффекта', 'Пилот приостановлен', 'Пилот прекращен', 'Передан в продажи', 'Завершен'],
  pilots: [
    { id: 'P-001', farmId: 'F-001', crop: 'Картофель', area: 2, control: 0.5, status: 'Испытание идет', owner: 'Агроном', start: datePlus(-24), next: datePlus(2), goal: 'Контроль состояния посадок', result: '', evidence: false },
    { id: 'P-002', farmId: 'F-006', crop: 'Малина', area: 1, control: 0.25, status: 'Ожидается промежуточный контроль', owner: 'Агроном', start: datePlus(-12), next: datePlus(0), goal: 'Наблюдение за развитием', result: '', evidence: false },
    { id: 'P-003', farmId: 'F-003', crop: 'Яблоня', area: 1, control: 0.3, status: 'Результат получен', owner: 'Агроном', start: datePlus(-70), next: datePlus(1), goal: 'Сравнение участков', result: 'Получены фото, требуется количественная оценка', evidence: true },
    { id: 'P-004', farmId: 'F-002', crop: 'Томат', area: 0.2, control: 0.1, status: 'Ожидается согласование', owner: 'Агроном', start: datePlus(-2), next: datePlus(3), goal: 'Подготовка протокола', result: '', evidence: false },
  ],
  applications: [
    { id: 'A-001', pilotId: 'P-001', date: datePlus(-19), method: 'По листу', dilution: 'По утвержденному протоколу', comment: 'контроль условий', result: '' },
    { id: 'A-002', pilotId: 'P-001', date: datePlus(-8), method: 'Под корень', dilution: 'По утвержденному протоколу', comment: 'вторая обработка', result: '' },
    { id: 'A-003', pilotId: 'P-002', date: datePlus(-6), method: 'По листу', dilution: 'По утвержденному протоколу', comment: 'запросить фото', result: '' },
  ],
  knowledge: [
    { id: 'K-001', title: 'BIOTORF: как объяснять ценность продукта', category: 'Продажи', crop: 'Все культуры', status: 'Утверждено', version: 1, owner: 'РОП', public: true, summary: 'Начинайте разговор с агрозадачи, площади, культуры и ожидаемого результата. Не обещайте урожайность без подтвержденного локального испытания.', source: 'Стратегия BIOTORF, раздел 7' },
    { id: 'K-002', title: 'Первый разговор с хозяйством — чек-лист', category: 'Продажи', crop: 'Все культуры', status: 'Утверждено', version: 1, owner: 'РОП', public: false, summary: 'Уточнить регион, площадь, культуру, текущую технологию, проблему, контакт агронома, удобное время следующего звонка.', source: 'Регламент управления' },
    { id: 'K-003', title: 'Ответ на возражение «дорого»', category: 'Продажи', crop: 'Все культуры', status: 'Утверждено', version: 1, owner: 'РОП', public: false, summary: 'Сравнивать не цену упаковки, а расходы на гектар и подтвержденную экономику применения. Не обещать окупаемость заранее.', source: 'Стратегия BIOTORF' },
    { id: 'K-004', title: 'Протокол пилота с контрольным участком', category: 'Агрономия', crop: 'Все культуры', status: 'На проверке', version: 1, owner: 'Агроном', public: false, summary: 'Фиксировать культуру, площадь, сопоставимый контроль, условия, даты, обработку и единые параметры измерения. Конкретные нормы утверждает агроном.', source: 'Регламент + стратегия' },
    { id: 'K-005', title: 'Фото ДО / ПОСЛЕ и разрешение на кейс', category: 'Агрономия', crop: 'Все культуры', status: 'Утверждено', version: 1, owner: 'Агроном', public: false, summary: 'Одинаковый ракурс, даты, описание условий, связь с протоколом и отдельное согласие хозяйства на публикацию.', source: 'Стратегия BIOTORF' },
    { id: 'K-006', title: 'Составление коммерческого предложения', category: 'Продажи', crop: 'Все культуры', status: 'Черновик', version: 1, owner: 'РОП', public: false, summary: 'Указать площадь, задачу, подтвержденную схему, SKU, объем, цену по действующей версии и следующий шаг.', source: 'Внутренний шаблон' },
    { id: 'K-007', title: 'AGRO: рецептура производства концентрата', category: 'Агрономия', crop: 'Все культуры', status: 'Утверждено', version: 1, owner: 'Агроном', public: false, summary: 'Исходная модель производства: одна часть пасты + четыре части воды. Это не является нормой внесения на поле.', source: 'Файл себестоимости 07.10.2026' },
    { id: 'K-008', title: 'HOME: рецептура производства', category: 'Агрономия', crop: 'Все культуры', status: 'Утверждено', version: 1, owner: 'Агроном', public: false, summary: 'Исходная модель производства HOME: 1 часть пасты + 1 часть воды. Перед промышленным применением требуется утвержденная спецификация.', source: 'Файл себестоимости 07.10.2026' },
  ],
  social: [
    { id: 'SOC-001', title: 'Картофель: наблюдения по пилоту', channel: 'Instagram', kind: 'Карусель', pilotId: 'P-001', date: datePlus(2), caption: 'сравнение состояния растений; результаты будут опубликованы только после проверки агрономом.', media: '', publicUrl: '', consent: 'Нет', caseApproved: 'Нет', status: 'Черновик', owner: 'Маркетолог' },
    { id: 'SOC-002', title: 'Контрольный участок: зачем он нужен', channel: 'Instagram', kind: 'Reels', pilotId: 'P-002', date: datePlus(5), caption: 'объясняем методику сравнения без обещания конкретного прироста урожая.', media: '', publicUrl: '', consent: 'Да', caseApproved: 'Нет', status: 'На согласовании', owner: 'Маркетолог' },
    { id: 'SOC-003', title: 'BIOTORF: вопросы и ответы', channel: 'Instagram', kind: 'Пост', pilotId: 'Без привязки', date: datePlus(8), caption: 'рубрика частых вопросов о продукте, основанная на утвержденных материалах.', media: '', publicUrl: '', consent: 'Да', caseApproved: 'Да', status: 'Готово к публикации', owner: 'Маркетолог' },
  ],
  skus: [
    { id: 'AG-10', name: 'AGRO 10 л', line: 'AGRO', pack: 10, recipe: '1:4', status: 'В модели' },
    { id: 'AG-05', name: 'AGRO 5 л', line: 'AGRO', pack: 5, recipe: '1:4', status: 'В модели' },
    { id: 'AG-01', name: 'AGRO 1 л', line: 'AGRO', pack: 1, recipe: '1:4', status: 'В модели' },
    { id: 'HO-01', name: 'HOME 1 л', line: 'HOME', pack: 1, recipe: '1:1', status: 'В модели' },
    { id: 'HO-02', name: 'HOME 0,2 л', line: 'HOME', pack: 0.2, recipe: '1:1', status: 'В модели' },
  ],
  cost: { paste_rub: 420, fx_kgs_rub: 1.0249, inbound_per_l_paste: 30, local_per_l_paste: 15, agro_mfg: 15, home_mfg: 25, fixed_month: 450000, scenario_volume: 5000, source: 'Калькуляция 07.10.2026 — допущения, не утвержденный прайс' },
  warehouse: [
    { id: 'S-001', sku: 'AG-10', qty: 150, reserved: 30, unit: 'шт.', warehouse: 'Основной' },
    { id: 'S-002', sku: 'AG-05', qty: 210, reserved: 35, unit: 'шт.', warehouse: 'Основной' },
    { id: 'S-003', sku: 'AG-01', qty: 400, reserved: 100, unit: 'шт.', warehouse: 'Основной' },
    { id: 'S-004', sku: 'HO-01', qty: 165, reserved: 20, unit: 'шт.', warehouse: 'Основной' },
    { id: 'S-005', sku: 'HO-02', qty: 800, reserved: 50, unit: 'шт.', warehouse: 'Основной' },
  ],
  stockMoves: [],
  production: [
    { id: 'PR-001', sku: 'AG-10', qty: 100, status: 'План', date: datePlus(3), lot: 'LOT-AG-2610-01' },
    { id: 'PR-002', sku: 'HO-01', qty: 75, status: 'В работе', date: datePlus(4), lot: 'LOT-HO-2610-01' },
  ],
  orders: [
    { id: 'SO-001', farmId: 'F-001', sku: 'AG-10', qty: 25, amount: 210000, status: 'Оплачен', date: datePlus(-9) },
    { id: 'SO-002', farmId: 'F-003', sku: 'AG-05', qty: 20, amount: 83000, status: 'Доставлен', date: datePlus(-18) },
    { id: 'SO-003', farmId: 'F-005', sku: 'AG-10', qty: 15, amount: 133000, status: 'Ожидает оплаты', date: datePlus(-1) },
  ],
  shipments: [
    { id: 'SH-001', orderId: 'SO-002', status: 'Доставлен', carrier: 'Перевозчик', planned: datePlus(-17), actual: datePlus(-16) },
    { id: 'SH-002', orderId: 'SO-001', status: 'К отправке', carrier: 'Не назначен', planned: datePlus(2), actual: '' },
  ],
  invoices: [
    { id: 'INV-001', orderId: 'SO-001', amount: 210000, paid: true, due: datePlus(-3), status: 'Оплачен' },
    { id: 'INV-002', orderId: 'SO-002', amount: 83000, paid: true, due: datePlus(-10), status: 'Оплачен' },
    { id: 'INV-003', orderId: 'SO-003', amount: 133000, paid: false, due: datePlus(7), status: 'Ожидается оплата' },
  ],
  payments: [],
  tasks: [
    { id: 'T-001', title: 'Запросить фото и замеры', who: 'Агроном', due: datePlus(0), status: 'В работе', object: 'P-002', priority: 'Высокий' },
    { id: 'T-002', title: 'Согласовать предложение по картофелю', who: 'Менеджер', due: datePlus(1), status: 'В работе', object: 'D-101', priority: 'Высокий' },
    { id: 'T-003', title: 'Получить обратную связь по саду', who: 'Менеджер', due: datePlus(-2), status: 'В работе', object: 'F-003', priority: 'Средний' },
    { id: 'T-004', title: 'Проверить отгрузку', who: 'Операционный', due: datePlus(2), status: 'Новая', object: 'SH-002', priority: 'Средний' },
    { id: 'T-005', title: 'Проверить статью по пилотам', who: 'Агроном', due: datePlus(3), status: 'Новая', object: 'K-004', priority: 'Средний' },
  ],
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