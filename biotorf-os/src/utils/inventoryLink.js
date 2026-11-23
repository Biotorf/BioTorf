export function inventoryLink(movement, sourceCollection, sourceId, orderId) {
  const query = new URLSearchParams({ movement, sourceCollection, sourceId });
  if (orderId) query.set('orderId', orderId);
  return '#/warehouse?' + query;
}
