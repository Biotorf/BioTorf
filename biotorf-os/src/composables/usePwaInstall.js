import { ref, onMounted } from 'vue';

// Общий обработчик события beforeinstallprompt: без него Chrome/Edge
// никогда не покажут кнопку «Установить» и не дадут программно запустить установку.
let deferredPrompt = null;
const canInstall = ref(false);
const installed = ref(false);

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    canInstall.value = true;
  });

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    canInstall.value = false;
    installed.value = true;
  });
}

export function usePwaInstall() {
  async function promptInstall() {
    if (!deferredPrompt) return false;
    deferredPrompt.prompt();
    try {
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'accepted') {
        canInstall.value = false;
        installed.value = true;
      }
    } catch (_) { /* пользователь закрыл диалог — ничего страшного */ }
    deferredPrompt = null;
    return true;
  }

  // Уже запущено как установленное приложение?
  const isStandalone =
    typeof window !== 'undefined' &&
    (window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true);

  onMounted(() => {
    if (isStandalone) installed.value = true;
  });

  return { canInstall, installed, promptInstall, isStandalone };
}
