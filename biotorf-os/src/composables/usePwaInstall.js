import { ref, computed, onMounted } from 'vue';

// Общий обработчик события beforeinstallprompt: без него Chrome/Edge
// никогда не покажут кнопку «Установить» и не дадут программно запустить установку.
let deferredPrompt = null;
const canInstall = ref(false);
const installed = ref(false);
const installHint = ref(false);   // установлен прямо сейчас → показываем подсказку про ярлык

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
    installHint.value = true;
    try { localStorage.setItem('biotorf.pwa.installed', '1'); } catch { /* noop */ }
    setTimeout(() => { installHint.value = false; }, 12000);
  });
}

export function usePwaInstall() {
  async function promptInstall() {
    if (!deferredPrompt) {
      // Браузер уже отдал событие или страница открыта как приложение —
      // подсказываем ручной путь установки вместо «мёртвой» кнопки.
      installHint.value = true;
      setTimeout(() => { installHint.value = false; }, 12000);
      return false;
    }
    try {
      await deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'dismissed') {
        // Пользователь отменил диалог — НЕ скрываем кнопку: deferredPrompt
        // обнулился, но при следующем визите браузер снова даёт шанс установить,
        // а до тех пор показываем подсказку с ручным способом.
        deferredPrompt = null;
        installHint.value = true;
        setTimeout(() => { installHint.value = false; }, 12000);
        return false;
      }
      // accepted: итог подтвердит событие appinstalled
    } catch (_) { /* пользователь закрыл диалог — ничего страшного */ }
    deferredPrompt = null;
    return true;
  }

  // Уже запущено как установленное приложение?
  const isStandalone =
    typeof window !== 'undefined' &&
    (window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true);

  // Кнопку показываем, если установка доступна ИЛИ приложение ещё не установлено
  // (после отмены диалога подсказываем ручной способ через installHint).
  const showInstallButton = computed(
    () => canInstall.value || (!installed.value && !isStandalone)
  );

  onMounted(() => {
    if (isStandalone) installed.value = true;
    else if (typeof localStorage !== 'undefined' && localStorage.getItem('biotorf.pwa.installed') === '1') {
      installed.value = true;   // уже ставили раньше из этого браузера — кнопку прячем
    }
  });

  return { canInstall, installed, installHint, showInstallButton, promptInstall, isStandalone };
}
