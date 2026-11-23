export const CRM_PHOTO_COLLECTIONS = new Set([
  'farms', 'skus', 'pilots', 'production', 'media', 'applications', 'contacts', 'orders',
]);

export function crmPhotoLink(collection, recordId) {
  return '#/registry?' + new URLSearchParams({ table: collection, id: recordId, section: 'photos' });
}
