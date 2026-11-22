const PENDING_KEY = 'biotorf.crm.pending.v1';
const queues = new WeakMap();

export function snapshot(data, collections) {
  return Object.fromEntries(collections.map((coll) => [coll, new Map(
    (data[coll] || []).filter((row) => row && row.id != null).map(({ _updatedAt, ...row }) => [
      String(row.id), { revision: _updatedAt || null, content: JSON.stringify(row) },
    ]),
  )]));
}

export function loadCrmSync(data, collections) {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(PENDING_KEY) || '{}'); } catch { /* fresh cache */ }
  return {
    baseline: snapshot(data, collections),
    supportsDelta: false,
    pending: Object.fromEntries(collections.map((coll) => [
      coll, new Map((Array.isArray(saved?.[coll]) ? saved[coll] : [])
        .filter((row) => row?.id != null)
        .map((row) => [String(row.id), row])),
    ])),
  };
}

export function captureChanges(sync, data, collections, trackDeletes = false) {
  const next = snapshot(data, collections);
  for (const coll of collections) {
    const previous = sync.baseline[coll];
    const pending = sync.pending[coll];
    for (const [id, row] of next[coll]) {
      if (row.content === previous.get(id)?.content) continue;
      const rev = pending.has(id) ? pending.get(id)._expectedRev : previous.get(id)?.revision ?? null;
      pending.set(id, { ...JSON.parse(row.content), id, _expectedRev: rev });
    }
    if (trackDeletes) {
      for (const [id, row] of previous) {
        if (next[coll].has(id)) continue;
        const rev = pending.has(id) ? pending.get(id)._expectedRev : row.revision;
        // A create immediately followed by a delete can already be in flight.
        pending.set(id, { id, _expectedRev: rev, _delete: true });
      }
    }
  }
  Object.assign(sync.baseline, next);
}

export function persistPending(sync) {
  const pending = Object.fromEntries(Object.entries(sync.pending)
    .filter(([, changes]) => changes.size)
    .map(([coll, changes]) => [coll, [...changes.values()]]));
  try { localStorage.setItem(PENDING_KEY, JSON.stringify(pending)); } catch { /* storage disabled */ }
}

export function crmPayload(sync) {
  return Object.fromEntries(Object.entries(sync.pending)
    .filter(([, changes]) => changes.size)
    .map(([coll, changes]) => [coll, [...changes.values()]]));
}

export function hasCrmChanges(sync) {
  return Object.values(sync.pending).some((rows) => rows.size);
}

export function acceptCrmState(sync, local, remote, collections, sent = {}) {
  for (const coll of collections) {
    if (!Array.isArray(remote[coll])) continue;
    const server = new Map(remote[coll].map((record) => [String(record.id), record]));
    const pending = sync.pending[coll];
    for (const change of sent[coll] || []) {
      const newer = pending.get(change.id);
      if (newer === change) pending.delete(change.id);
      else if (newer) pending.set(change.id, {
        ...newer, _expectedRev: server.get(change.id)?._updatedAt ?? null,
      });
    }
    for (const change of pending.values()) {
      if (change._delete) server.delete(change.id);
      else {
        const { _expectedRev, ...record } = change;
        server.set(change.id, { ...record, _updatedAt: _expectedRev });
      }
    }
    local[coll] = [...server.values()];
  }
  Object.assign(sync.baseline, snapshot(local, collections));
}

export function serializeCrm(sync, work) {
  const previous = queues.get(sync) || Promise.resolve();
  const next = previous.catch(() => {}).then(work);
  queues.set(sync, next);
  return next;
}
