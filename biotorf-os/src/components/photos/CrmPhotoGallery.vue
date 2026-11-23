<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue';
import { CRM_PHOTO_ACCEPT, CRM_PHOTO_LIMIT, CRM_PHOTO_MAX_BYTES, crmPhotosApi, isCrmPhotoType } from '@/api/crmPhotosClient';
import CrmPhotoThumbnail from './CrmPhotoThumbnail.vue';

const props = defineProps({
  collection: { type: String, required: true },
  recordId: { type: [String, Number], required: true },
  recordName: { type: String, default: '' },
  editable: Boolean,
});
const emit = defineEmits(['changed', 'loaded']);
const heading = useId();
const galleryHeading = ref(null);
const fileInput = ref(null);
const lightbox = ref(null);
const closeButton = ref(null);
const training = inject('trainingActive', ref(false));
const photos = ref([]);
const queue = ref([]);
const available = ref(false);
const serverCanEdit = ref(false);
const operation = ref('');
const loading = ref(false);
const progress = ref(null);
const loadError = ref('');
const actionError = ref('');
const feedback = ref('');
const deleting = ref(null);
const openedId = ref('');
const openedSrc = ref('');
const imageError = ref(false);
let activeRecord;
let restoreFocus;
let removalTile;

const canEdit = computed(() => props.editable && serverCanEdit.value && !training.value);
const room = computed(() => Math.max(0, CRM_PHOTO_LIMIT - photos.value.length - queue.value.length));
const cover = computed(() => photos.value.find((photo) => photo.isCover) || photos.value[0] || null);
const orderedPhotos = computed(() => cover.value
  ? [cover.value, ...photos.value.filter((photo) => photo.id !== cover.value.id)]
  : []);
const index = computed(() => orderedPhotos.value.findIndex((photo) => photo.id === openedId.value));
const openedPhoto = computed(() => orderedPhotos.value[index.value]);
const nameFor = (photo) => photo?.name || 'Фото';

function explain(error) {
  if (error?.name === 'TimeoutError' || error instanceof TypeError) return 'Нет связи с сервером. Попробуйте ещё раз.';
  return error?.message || 'Попробуйте ещё раз.';
}

function applyGallery(result, event) {
  if (!Array.isArray(result?.items)) throw new Error('Сервер вернул неполный список фото. Попробуйте ещё раз.');
  photos.value = result.items;
  serverCanEdit.value = result.canEdit;
  available.value = true;
  emit(event, cover.value);
}

async function load() {
  const current = activeRecord;
  if (current.id === '' || current.id == null) return;
  loading.value = true;
  loadError.value = '';
  try {
    const result = await crmPhotosApi.list(current.collection, current.id, { signal: current.signal });
    if (!current.signal.aborted) applyGallery(result, 'loaded');
  } catch (error) {
    if (!current.signal.aborted) loadError.value = `Не удалось загрузить фото. ${explain(error)}`;
  } finally {
    if (!current.signal.aborted) loading.value = false;
  }
}

function clearQueue() {
  for (const entry of queue.value) URL.revokeObjectURL(entry.src);
  queue.value = [];
}

watch(() => [props.collection, props.recordId], ([collection, id], _, cleanup) => {
  const controller = new AbortController();
  activeRecord = { collection, id, signal: controller.signal };
  cleanup(() => controller.abort());
  clearQueue();
  closeViewer();
  photos.value = [];
  available.value = false;
  serverCanEdit.value = false;
  actionError.value = '';
  feedback.value = '';
  operation.value = '';
  progress.value = null;
  deleting.value = null;
  removalTile = null;
  load();
}, { immediate: true });

onBeforeUnmount(clearQueue);

function chooseFiles() {
  if (canEdit.value && room.value && !operation.value) fileInput.value?.click();
}

function addFiles(files) {
  if (!canEdit.value || operation.value) return;
  const errors = [];
  feedback.value = '';
  for (const file of files) {
    if (!isCrmPhotoType(file.type) && (file.type || !/\.(jpe?g|png|webp)$/i.test(file.name))) {
      errors.push(`«${file.name}» — используйте JPG, PNG или WebP.`);
    } else if (!file.size || file.size > CRM_PHOTO_MAX_BYTES) {
      errors.push(`«${file.name}» — выберите непустое фото до 8 МБ.`);
    } else if (queue.value.some(({ file: saved }) => saved.name === file.name && saved.size === file.size && saved.lastModified === file.lastModified)) {
      continue;
    } else if (!room.value) {
      errors.push(`В карточке может быть до ${CRM_PHOTO_LIMIT} фото.`);
      break;
    } else {
      const src = URL.createObjectURL(file);
      queue.value.push({ file, src, error: '' });
    }
  }
  actionError.value = errors.join(' ');
}

function changeFiles(event) {
  addFiles(event.currentTarget.files);
  event.currentTarget.value = '';
}

function discardFile(entry) {
  URL.revokeObjectURL(entry.src);
  queue.value = queue.value.filter(({ src }) => src !== entry.src);
}

async function upload() {
  if (!canEdit.value || operation.value || !queue.value.length) return;
  const pending = [...queue.value];
  const current = activeRecord;
  operation.value = 'upload';
  actionError.value = '';
  feedback.value = '';
  let saved = 0;
  for (const [fileIndex, entry] of pending.entries()) {
    if (current.signal.aborted) return;
    const status = { current: fileIndex + 1, total: pending.length, percent: 0 };
    progress.value = status;
    entry.error = '';
    try {
      const result = await crmPhotosApi.upload(current.collection, current.id, entry.file, {
        signal: current.signal,
        onProgress: (percent) => {
          if (!current.signal.aborted) progress.value = { ...status, percent };
        },
      });
      if (current.signal.aborted) return;
      applyGallery(result, 'changed');
      discardFile(entry);
      saved++;
    } catch (error) {
      if (current.signal.aborted) return;
      entry.error = explain(error);
    }
  }
  operation.value = '';
  progress.value = null;
  if (saved) feedback.value = `Сохранено фото: ${saved} из ${pending.length}.`;
}

async function changePhoto(photo, action) {
  if (!canEdit.value || operation.value) return;
  const current = activeRecord;
  operation.value = action;
  actionError.value = '';
  feedback.value = '';
  let completed = false;
  try {
    const result = await crmPhotosApi[action](current.collection, current.id, photo.id, { signal: current.signal });
    if (current.signal.aborted) return;
    applyGallery(result, 'changed');
    deleting.value = null;
    removalTile = null;
    feedback.value = action === 'remove' ? 'Фото удалено.' : 'Обложка обновлена.';
    completed = true;
  } catch (error) {
    if (!current.signal.aborted) actionError.value = `Не удалось сохранить изменение. ${explain(error)}`;
  } finally {
    if (!current.signal.aborted) {
      operation.value = '';
      if (completed) await nextTick();
      if (completed && !current.signal.aborted) galleryHeading.value?.focus({ preventScroll: true });
    }
  }
}

async function confirmRemove(photo, event) {
  removalTile = event.currentTarget.closest('.photo-tile');
  deleting.value = photo;
  await nextTick();
  removalTile?.querySelector('.cancel-removal')?.focus();
}

async function cancelRemove() {
  const tile = removalTile;
  deleting.value = null;
  removalTile = null;
  await nextTick();
  tile?.querySelector('.request-removal')?.focus();
}

async function openViewer(photo, event) {
  restoreFocus = event.currentTarget;
  openedId.value = photo.id;
  await nextTick();
  if (!lightbox.value?.open) lightbox.value?.showModal();
  closeButton.value?.focus();
}

function closeViewer() {
  if (lightbox.value?.open) lightbox.value.close();
  else openedId.value = '';
}

function viewerClosed() {
  openedId.value = '';
  if (restoreFocus?.isConnected) restoreFocus.focus();
  restoreFocus = null;
}

function stepPhoto(step) {
  const items = orderedPhotos.value;
  if (items.length < 2) return;
  openedId.value = items[(index.value + step + items.length) % items.length].id;
}

function clearOpenedImage() {
  if (openedSrc.value) URL.revokeObjectURL(openedSrc.value);
  openedSrc.value = '';
}

watch(openedPhoto, async (photo, _, cleanup) => {
  clearOpenedImage();
  imageError.value = false;
  if (!photo) return;
  const current = activeRecord;
  const controller = new AbortController();
  const signal = AbortSignal.any([controller.signal, current.signal]);
  cleanup(() => { controller.abort(); clearOpenedImage(); });
  try {
    const blob = await crmPhotosApi.asset(current.collection, current.id, photo.id, { signal });
    if (!signal.aborted) openedSrc.value = URL.createObjectURL(blob);
  } catch {
    if (!signal.aborted) imageError.value = true;
  }
});
</script>

<template>
  <section class="panel photo-gallery" :aria-labelledby="heading" data-tour="record-photos">
    <div class="gallery-header">
      <div>
        <h2 :id="heading" ref="galleryHeading" tabindex="-1">Фотографии</h2>
        <p v-if="available" class="counter">{{ photos.length }} из {{ CRM_PHOTO_LIMIT }}</p>
      </div>
      <div v-if="canEdit" class="photo-actions">
        <input ref="fileInput" type="file" :accept="CRM_PHOTO_ACCEPT" multiple hidden @change="changeFiles" />
        <button type="button" class="btn primary" data-tour="record-photos-upload"
          :disabled="!room || !!operation" @click="chooseFiles">＋ Добавить фото</button>
      </div>
    </div>

    <p v-if="loading" class="gallery-note" role="status">Загружаем фотографии…</p>
    <div v-else-if="loadError" class="gallery-message">
      <p class="gallery-error" role="alert">{{ loadError }}</p>
      <button type="button" class="btn slim" @click="load">Повторить</button>
    </div>
    <div v-else-if="!photos.length && !queue.length" class="gallery-placeholder">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="3" />
        <path d="m3.5 16 4.7-4.7 4 4 3-3 5.3 5.3" />
        <circle cx="15.5" cy="8.5" r="1.3" />
      </svg>
      <div>
        <strong>Фото пока нет</strong>
        <p v-if="canEdit">Первый снимок станет обложкой карточки.</p>
      </div>
    </div>
    <template v-if="available">
      <p v-if="canEdit" class="gallery-note">JPG, PNG или WebP, до 8 МБ на фото.</p>
      <p v-if="actionError" class="gallery-error" role="alert">{{ actionError }}</p>
      <p v-if="feedback" class="gallery-feedback" role="status">{{ feedback }}</p>

      <ul v-if="orderedPhotos.length" class="gallery-grid" aria-label="Сохранённые фотографии">
        <li v-for="photo in orderedPhotos" :key="photo.id" class="photo-tile">
          <button type="button" class="photo-preview" :aria-label="`Открыть фото «${nameFor(photo)}»`" @click="openViewer(photo, $event)">
            <CrmPhotoThumbnail :collection="collection" :record-id="recordId" :cover-id="photo.id" />
            <span v-if="photo.id === cover?.id" class="cover-label">Обложка</span>
          </button>
          <div class="photo-details">
            <span :title="nameFor(photo)">{{ nameFor(photo) }}</span>
            <div v-if="canEdit" class="photo-actions">
              <template v-if="deleting?.id === photo.id">
                <p class="confirm-text">Удалить это фото?</p>
                <button type="button" class="btn slim danger-action" :disabled="!!operation"
                  :aria-label="`Удалить фото «${nameFor(photo)}» навсегда`" @click="changePhoto(photo, 'remove')">Удалить</button>
                <button type="button" class="btn slim ghost cancel-removal" :disabled="!!operation" @click="cancelRemove">Отмена</button>
              </template>
              <template v-else>
                <button v-if="photo.id !== cover?.id" type="button" class="btn slim ghost" :disabled="!!operation || !!deleting"
                  :aria-label="`Сделать обложкой «${nameFor(photo)}»`" @click="changePhoto(photo, 'makeCover')">На обложку</button>
                <button type="button" class="btn slim ghost danger-action request-removal" :disabled="!!operation || !!deleting"
                  :aria-label="`Удалить фото «${nameFor(photo)}»`" @click="confirmRemove(photo, $event)">Удалить</button>
              </template>
            </div>
          </div>
        </li>
      </ul>

      <section v-if="canEdit && queue.length" class="upload-queue" aria-label="Фото для загрузки">
        <h3>Готовы к загрузке</h3>
        <ul class="queued-list">
          <li v-for="entry in queue" :key="entry.src" class="queued-file">
            <img :src="entry.src" alt="" decoding="async" />
            <div>
              <span>{{ entry.file.name }}</span>
              <p v-if="entry.error" class="gallery-error" role="alert">{{ entry.error }}</p>
            </div>
            <button type="button" class="btn slim ghost" :disabled="!!operation"
              :aria-label="`Убрать файл «${entry.file.name}»`" @click="discardFile(entry)">Убрать</button>
          </li>
        </ul>
        <div v-if="progress" class="upload-progress">
          <span role="status">Загружаем фото {{ progress.current }} из {{ progress.total }}</span>
          <progress :value="progress.percent" max="100" aria-label="Ход загрузки фото" />
        </div>
        <div class="photo-actions">
          <button type="button" class="btn primary" :disabled="!!operation" @click="upload">Загрузить фото</button>
          <button type="button" class="btn ghost" :disabled="!!operation" @click="clearQueue">Очистить список</button>
        </div>
      </section>
    </template>

    <Teleport to="body">
      <dialog ref="lightbox" class="photo-lightbox" :aria-label="recordName ? `Фотографии: ${recordName}` : 'Просмотр фотографий'"
        @close="viewerClosed" @click.self="closeViewer" @keydown.left.prevent="stepPhoto(-1)" @keydown.right.prevent="stepPhoto(1)">
        <div v-if="openedPhoto" class="viewer-content">
          <div class="viewer-header">
            <div>
              <h2 :title="nameFor(openedPhoto)">{{ nameFor(openedPhoto) }}</h2>
              <p v-if="orderedPhotos.length > 1">{{ index + 1 }} из {{ orderedPhotos.length }}</p>
            </div>
            <button ref="closeButton" type="button" class="btn ghost slim" @click="closeViewer">Закрыть</button>
          </div>
          <div class="viewer-image">
            <img v-if="openedSrc && !imageError" :src="openedSrc" :alt="nameFor(openedPhoto)" @error="imageError = true" />
            <p v-else-if="imageError" class="gallery-error" role="alert">Не удалось открыть фото.</p>
            <p v-else class="gallery-note" role="status">Загружаем фото…</p>
          </div>
          <div v-if="orderedPhotos.length > 1" class="viewer-buttons">
            <button type="button" class="btn" @click="stepPhoto(-1)">← Предыдущее</button>
            <button type="button" class="btn" @click="stepPhoto(1)">Следующее →</button>
          </div>
        </div>
      </dialog>
    </Teleport>
  </section>
</template>

<style scoped>
.photo-gallery { min-width: 0; }
.gallery-header, .photo-actions, .gallery-message, .viewer-header, .viewer-buttons {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.gallery-header, .viewer-header, .viewer-buttons { justify-content: space-between; }
.counter, .gallery-note, .confirm-text, .viewer-header p { color: var(--muted); font-size: .875rem; }
.counter, .gallery-error, .gallery-feedback, .confirm-text, .viewer-header p { margin: 0; }
.gallery-note { margin: 10px 0 0; }
.gallery-error { color: var(--danger-ink, #a23631); overflow-wrap: anywhere; }
.gallery-feedback { color: var(--accent-ink, var(--green)); }
.gallery-placeholder, .gallery-message, .gallery-error, .gallery-feedback { margin: 12px 0 0; }
.gallery-placeholder {
  padding: 16px;
  border: 1px dashed var(--control-border, var(--border));
  border-radius: 12px;
  background: var(--surface-soft, var(--bg));
  display: flex;
  align-items: center;
  gap: 12px;
}
.gallery-placeholder svg { flex: none; stroke: var(--green); stroke-width: 1.5; }
.gallery-placeholder p { margin: 2px 0 0; color: var(--muted); }
.gallery-grid, .queued-list { list-style: none; padding: 0; margin: 12px 0 0; }
.gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 160px), 1fr)); gap: 12px; }
.photo-tile { min-width: 0; align-self: start; border: 1px solid var(--border); border-radius: 12px; overflow: clip; }
.photo-preview { display: block; width: 100%; position: relative; border: 0; padding: 0; background: none; }
.photo-preview:focus-visible { outline: 3px solid var(--green); outline-offset: -4px; }
.cover-label {
  position: absolute;
  inset: 8px auto auto 8px;
  border-radius: 50px;
  padding: 3px 8px;
  font-size: .75rem;
  color: #fff;
  background: #194331;
  font-weight: 650;
}
.photo-details { padding: 8px; background: var(--surface-soft, var(--bg)); }
.photo-details > span, .queued-file span, .viewer-header h2 { display: block; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.photo-details > span { margin-bottom: 4px; }
.photo-details .photo-actions { gap: 4px; }
.confirm-text { width: 100%; }
.danger-action { color: var(--danger-ink, #a23631); }
.upload-queue { margin-top: 12px; padding: 12px; border: 1px solid var(--border); border-radius: 12px; }
.upload-queue h3 { margin-bottom: 6px; }
.queued-list { margin: 0 0 12px; }
.queued-file { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border); }
.queued-file img { width: 44px; height: 44px; border-radius: 6px; object-fit: cover; }
.queued-file .gallery-error { margin-top: 0; }
.upload-progress { display: grid; gap: 4px; margin: 8px 0 12px; }
.upload-progress progress { width: 100%; accent-color: var(--green); }
.photo-lightbox {
  width: min(760px, calc(100vw - 24px));
  max-height: calc(100dvh - 24px);
  padding: 0;
  border: 1px solid var(--control-border, var(--border));
  border-radius: 16px;
  background: var(--panel);
  color: var(--ink);
  overscroll-behavior: contain;
}
.photo-lightbox::backdrop { background: rgb(7 24 17 / 74%); }
.viewer-content { display: grid; gap: 12px; padding: 14px; }
.viewer-header { flex-wrap: nowrap; }
.viewer-header > div { min-width: 0; }
.viewer-image { min-height: 140px; background: var(--surface-soft, var(--bg)); border-radius: 9px; display: grid; place-items: center; overflow: hidden; }
.viewer-image img { display: block; max-width: 100%; max-height: min(66dvh, 640px); object-fit: contain; }
@media (max-width: 450px) {
  .photo-gallery { padding: 12px; }
  .gallery-grid { grid-template-columns: repeat(auto-fill, minmax(min(100%, 110px), 1fr)); }
}
</style>
