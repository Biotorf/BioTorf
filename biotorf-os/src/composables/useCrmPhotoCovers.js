import { ref, toValue, watch } from 'vue';
import { crmPhotosApi } from '@/api/crmPhotosClient';

export function useCrmPhotoCovers(collection, recordIds) {
  const covers = ref(new Map());
  let currentUpdates;

  function setCover(recordId, cover) {
    const id = String(recordId);
    if (cover) covers.value.set(id, cover);
    else covers.value.delete(id);
    currentUpdates?.set(id, cover);
  }

  watch(() => toValue(recordIds), (ids, _previous, onCleanup) => {
    const idsToLoad = [...new Set(ids.map(String))];
    if (!idsToLoad.length) {
      covers.value = new Map();
      return;
    }
    const request = new AbortController();
    const updates = new Map();
    currentUpdates = updates;
    const timer = setTimeout(async () => {
      try {
        const { items } = await crmPhotosApi.covers(collection, idsToLoad, { signal: request.signal });
        if (request.signal.aborted) return;
        const next = new Map(Object.entries(items || {}));
        for (const [id, cover] of updates) {
          if (cover) next.set(id, cover);
          else next.delete(id);
        }
        covers.value = next;
      } catch {
        // Existing thumbnails remain usable if refreshing the covers fails.
      } finally {
        if (currentUpdates === updates) currentUpdates = null;
      }
    }, 100);
    onCleanup(() => {
      clearTimeout(timer);
      request.abort();
      if (currentUpdates === updates) currentUpdates = null;
    });
  }, { immediate: true });

  return { covers, setCover };
}
