export const CLIENT_TYPES = [
  'Частный покупатель', 'Компания', 'Агропроизводитель', 'Розничный магазин',
  'Оптовая база', 'Дилер', 'Дистрибьютор', 'Другой',
];

const personTypes = new Set(['частный покупатель', 'физическое лицо', 'физлицо', 'частное лицо']);

export function isPerson(type) {
  return personTypes.has(String(type || '').trim().toLowerCase());
}

export function clientInitials(name) {
  return String(name || '').trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'К';
}

export function phoneDigits(value) {
  return String(value || '').replace(/\D/g, '');
}

export function primaryContact(contacts) {
  return contacts.find((contact) => contact.primary === true || contact.primary === 1 || contact.primary === 'true') || contacts[0];
}

const referenceFields = {
  leadId: 'leads', journeyId: 'journeys', dealId: 'deals', pilotId: 'pilots',
  quoteId: 'quotes', orderId: 'orders', invoiceId: 'invoices', shipmentId: 'shipments',
};

const clientTables = [
  'contacts', 'leads', 'journeys', 'deals', 'pilots', 'quotes', 'orders',
  'invoices', 'payments', 'shipments', 'clientNotes', 'clientDocs', 'logistics',
];

// An explicit client ID wins. For imported records that lack one, follow their
// document references and exclude ambiguous links between different clients.
export function clientRecords(data, clientId) {
  const byTable = new Map(clientTables.map((table) => [
    table, new Map((data[table] || []).map((record) => [String(record.id), {
      record, client: record.farmId ? String(record.farmId) : '', neighbors: [],
      owners: new Set(),
    }])),
  ]));
  const queue = [];
  for (const [table, rows] of byTable) {
    for (const row of rows.values()) {
      if (row.client) {
        row.owners.add(row.client);
        queue.push([row, row.client]);
      }
      for (const [key, target] of Object.entries(referenceFields)) {
        // Shipments and orders point back to their route, and the route may
        // contain the only reference to a document created by a legacy client.
        const related = byTable.get(target).get(String(row.record[key] || ''));
        if (related && related !== row) {
          related.neighbors.push(row);
          if (table === 'journeys') row.neighbors.push(related);
        }
      }
    }
  }
  for (let index = 0; index < queue.length; index++) {
    const [row, owner] = queue[index];
    for (const related of row.neighbors) {
      if (related.client || related.owners.has(owner) || related.owners.size > 1) continue;
      related.owners.add(owner);
      queue.push([related, owner]);
    }
  }
  return Object.fromEntries([...byTable].map(([table, rows]) => [
    table, [...rows.values()].filter(({ owners }) => owners.size === 1 && owners.has(String(clientId)))
      .map(({ record }) => record),
  ]));
}
