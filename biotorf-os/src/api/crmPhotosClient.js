import { authHeaders } from './authClient';
import { COMMS_API_URL } from './commsClient';

export const CRM_PHOTO_LIMIT = 12;
export const CRM_PHOTO_MAX_BYTES = 8 * 1024 * 1024;
export const CRM_PHOTO_ACCEPT = 'image/jpeg,image/png,image/webp';

export function isCrmPhotoType(type) {
  return CRM_PHOTO_ACCEPT.split(',').includes(type);
}

function pathFor(collection, recordId, photoId) {
  return '/api/crm-photos/' + [collection, recordId, photoId]
    .filter((part) => part != null).map(encodeURIComponent).join('/');
}

function apiError(status, body) {
  const detail = body?.detail;
  const message = typeof detail === 'string' ? detail : detail?.message;
  const fallback = {
    401: 'Сеанс завершился. Войдите заново.',
    403: 'У вас нет доступа к этому фото.',
    404: 'Запись или фото не найдены.',
    413: 'Фото превышает 8 МБ.',
  };
  const error = new Error(message || fallback[status] || 'Сервер не смог обработать фото. Попробуйте ещё раз.');
  error.status = status;
  return error;
}

async function request(path, { signal, method = 'GET', image = false } = {}) {
  const timeout = AbortSignal.timeout(image ? 25000 : 12000);
  const response = await fetch(COMMS_API_URL + path, {
    method,
    headers: { ...authHeaders(), Accept: image ? CRM_PHOTO_ACCEPT : 'application/json' },
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });
  if (!response.ok) throw apiError(response.status, await response.json().catch(() => null));
  if (image) {
    const blob = await response.blob();
    if (!isCrmPhotoType(blob.type)) throw new Error('Не удалось открыть изображение.');
    return blob;
  }
  try {
    return await response.json();
  } catch {
    throw new Error('Сервер вернул неполный ответ. Попробуйте ещё раз.');
  }
}

function upload(collection, recordId, file, { signal, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', COMMS_API_URL + pathFor(collection, recordId));
    xhr.setRequestHeader('Accept', 'application/json');
    for (const [key, value] of Object.entries(authHeaders())) xhr.setRequestHeader(key, value);
    xhr.responseType = 'json';
    xhr.timeout = 90000;
    const abort = () => xhr.abort();
    signal?.addEventListener('abort', abort, { once: true });
    xhr.onloadend = () => signal?.removeEventListener('abort', abort);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300 && xhr.response) resolve(xhr.response);
      else reject(apiError(xhr.status, xhr.response));
    };
    xhr.onerror = () => reject(new Error('Связь с сервером прервалась. Попробуйте ещё раз.'));
    xhr.ontimeout = () => reject(new Error('Загрузка заняла слишком много времени. Попробуйте ещё раз.'));
    xhr.onabort = () => reject(new DOMException('Загрузка отменена.', 'AbortError'));
    const body = new FormData();
    body.append('file', file);
    xhr.send(body);
  });
}

export const crmPhotosApi = {
  list: (collection, recordId, options) => request(pathFor(collection, recordId), options),
  covers: (collection, ids, options) => {
    const params = new URLSearchParams();
    for (const id of new Set(ids.filter((value) => value != null && value !== '').map(String))) params.append('id', id);
    return params.size ? request(`${pathFor(collection)}?${params}`, options) : Promise.resolve({ items: {} });
  },
  asset: (collection, recordId, photoId, { thumbnail = false, signal } = {}) => request(
    `${pathFor(collection, recordId, photoId)}/content${thumbnail ? '?thumbnail=true' : ''}`,
    { signal, image: true },
  ),
  upload,
  makeCover: (collection, recordId, photoId, options) => request(pathFor(collection, recordId, photoId), { ...options, method: 'PATCH' }),
  remove: (collection, recordId, photoId, options) => request(pathFor(collection, recordId, photoId), { ...options, method: 'DELETE' }),
};
