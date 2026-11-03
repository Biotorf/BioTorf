<script setup>
// Экран входа/регистрации BIOTORF Business OS.
// Показывается только если бэкенд требует авторизацию (authState.required).
// Если сотрудников ещё нет (hasUsers=false) — первым регистрируется
// генеральный директор: его аккаунт создаётся автоматически с ролью director.
import { ref, computed, nextTick } from 'vue';
import { login, register, authState } from '@/api/authClient';
import { useUiStore } from '@/stores/ui';
import { usePwaInstall } from '@/composables/usePwaInstall';

const ui = useUiStore();
const emit = defineEmits(['session']);   // готовая сессия → App скрывает gate
const { installHint, showInstallButton, promptInstall } = usePwaInstall();

const mode = ref('login');            // login | register
const user = ref('');
const name = ref('');
const pass = ref('');
const pass2 = ref('');
const busy = ref(false);
const error = ref('');
const info = ref('');
const pendingSession = ref(null);     // сессия pending: можно заполнить профиль

const firstRun = computed(() => authState.required && !authState.hasUsers);

function switchMode(m) { mode.value = m; error.value = ''; info.value = ''; }

// Надёжный вход в сервис: применяем профиль в ui-стор, скрываем экран входа
// и подтягиваем данные с сервера — БЕЗ перезагрузки страницы.
async function enterService(res) {
  // токен уже сохранён в authState (applySession внутри login/register) —
  // применяем профиль, скрываем экран входа и подтягиваем данные.
  ui.applySession(authState.user || res);
  emit('session', res);
  await nextTick();
  try {
    const { useDbStore } = await import('@/stores/db');
    useDbStore().pullCrmState();
  } catch { /* noop */ }
  // страховка: если по какой-то причине экран не перерисовался (старый кэш
  // сборки на Render), через короткий таймаут обновляем страницу — пользователь
  // оказывается в сервисе автоматически, без ручного F5
  setTimeout(() => location.reload(), 800);
}

async function submit() {
  error.value = ''; info.value = '';
  if (!user.value.trim() || !pass.value) { error.value = 'Заполните логин и пароль'; return; }
  if (mode.value === 'register') {
    if (pass.value.length < 8) { error.value = 'Пароль — не короче 8 символов'; return; }
    if (pass.value !== pass2.value) { error.value = 'Пароли не совпадают'; return; }
  }
  busy.value = true;
  try {
    if (mode.value === 'login') {
      const res = await login(user.value.trim(), pass.value);
      // сразу перекидываем в сервис — без перезагрузки страницы
      await enterService(res);
      if (res.pending) {
        info.value = `Вы вошли как ожидающий подтверждения. Заполните профиль — генеральный директор увидит ваши данные и выдаст роль.`;
        pendingSession.value = res;
      }
    } else {
      const res = await register(user.value.trim(), pass.value, name.value.trim());
      if (res.firstAccount) {
        await enterService(res);   // первый аккаунт = директор, токен уже выдан
        return;
      }
      // зарегистрировались → сразу входим под этим же логином/паролем:
      // получаем pending-токен и можем заполнить профиль до подтверждения
      const lg = await login(res.login || user.value.trim(), pass.value);
      if (lg.token || lg.pending) {
        // сразу перекидываем в сервис (pending sees restricted UI + profile modal)
        await enterService(lg);
        pendingSession.value = lg;
        info.value = 'Аккаунт создан и ожидает подтверждения роли генеральным директором. Заполните профиль — директор увидит ваши данные.';
      } else {
        info.value = 'Аккаунт создан и ожидает подтверждения роли генеральным директором. Теперь войдите.';
        mode.value = 'login';
      }
    }
  } catch (e) {
    error.value = e.message || 'Сервер недоступен';
  } finally {
    busy.value = false;
  }
}

function enterPending() {
  if (pendingSession.value) enterService(pendingSession.value);
}
</script>

<template>
  <div class="gate">
    <form class="gate-card" @submit.prevent="submit">
      <div class="gate-brand"><span class="brand-mark">🌱</span><strong>BIOTORF BUSINESS OS</strong></div>

      <!-- установка приложения: показываем только до входа -->
      <button
        v-if="showInstallButton"
        class="install-hint"
        type="button"
        @click="promptInstall"
        title="Установить BIOTORF как приложение на компьютер"
      >⤓ Установить как приложение (ярлык на рабочем столе)</button>
      <p v-if="installHint" class="gate-note ok">
        Приложение установлено ✅ — ярлык появится на рабочем столе и в меню «Пуск»
        Windows автоматически. Если нужно именно <b>файл ярлыка (.lnk)</b>: правый клик
        по значку в панели задач → «Закрепить на панели задач», либо из меню браузера
    (⋮) → «Сохранить и поделиться» → «Создать ярлык…».
      </p>

      <h2>{{ mode === 'login' ? 'Вход для сотрудников' : 'Регистрация сотрудника' }}</h2>
      <p v-if="firstRun && mode === 'register'" class="gate-note ok">
        В системе пока нет ни одного аккаунта. Первый зарегистрированный
        сотрудник автоматически станет <b>генеральным директором</b> и сможет
        выдавать роли остальным.
      </p>
      <p v-else-if="firstRun" class="gate-note">
        Чтобы начать работу, зарегистрируйте первого сотрудника — он станет
        генеральным директором.
      </p>

      <div class="field">
        <label>Логин</label>
        <input v-model="user" class="input" autocomplete="username" placeholder="например, ivanov" />
      </div>
      <div v-if="mode === 'register'" class="field">
        <label>Имя сотрудника <span class="text-muted">(необязательно)</span></label>
        <input v-model="name" class="input" placeholder="Иван Петров" />
      </div>
      <div class="field">
        <label>Пароль</label>
        <input v-model="pass" class="input" type="password" autocomplete="current-password" />
      </div>
      <div v-if="mode === 'register'" class="field">
        <label>Повторите пароль</label>
        <input v-model="pass2" class="input" type="password" autocomplete="new-password" />
      </div>

      <p v-if="error" class="gate-note err">{{ error }}</p>
      <p v-if="info" class="gate-note ok">{{ info }}</p>

      <!-- после регистрации/входа pending: кнопка войти в мини-профиль -->
      <button v-if="pendingSession" class="btn primary" type="button" @click="enterPending">
        👤 Заполнить профиль →
      </button>
      <template v-else>
        <button class="btn primary" type="submit" :disabled="busy">
          {{ busy ? 'Проверка…' : (mode === 'login' ? 'Войти' : 'Зарегистрироваться') }}
        </button>

        <button v-if="!firstRun" class="btn ghost gate-switch" type="button"
                @click="switchMode(mode === 'login' ? 'register' : 'login')">
          {{ mode === 'login' ? 'Нет аккаунта? Регистрация' : 'Уже есть аккаунт? Вход' }}
        </button>
        <button v-else-if="mode === 'login'" class="btn ghost gate-switch" type="button" @click="switchMode('register')">
          Зарегистрировать генерального директора →
        </button>
      </template>
    </form>
  </div>
</template>

<style scoped>
.gate{min-height:100vh;display:grid;place-items:center;background:#0f2b21;padding:20px}
.gate-card{width:min(400px,100%);background:#fff;border-radius:16px;padding:28px 26px;box-shadow:0 20px 70px rgba(0,0,0,.35);display:flex;flex-direction:column;gap:12px}
.gate-brand{display:flex;align-items:center;gap:10px;margin-bottom:4px}
.gate-brand strong{letter-spacing:1.5px;font-size:14px;color:#214f37}
.gate-card h2{font-size:19px;margin-bottom:2px}
.gate-note{font-size:12px;color:#7a6840;background:#fffbec;border:1px solid #e7ddbf;border-radius:9px;padding:9px 11px;margin:0}
.gate-note.err{color:#b94337;background:#ffedea;border-color:#f0cfc9}
.gate-note.ok{color:#218468;background:#e5f5ee;border-color:#cfe9db}
.gate-card .btn.primary{margin-top:6px}
.gate-switch{font-size:12px}
.install-hint{border:1px dashed #863bff;background:#f5f0ff;color:#5b2bb8;border-radius:10px;padding:8px 12px;font-size:12.5px;cursor:pointer;transition:.15s}
.install-hint:hover{background:#ece2ff}
</style>
