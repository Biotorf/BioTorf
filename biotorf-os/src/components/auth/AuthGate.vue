<script setup>
// Экран входа/регистрации BIOTORF Business OS.
// Показывается только если бэкенд требует авторизацию (authState.required).
// Если сотрудников ещё нет (hasUsers=false) — первым регистрируется
// генеральный директор: его аккаунт создаётся автоматически с ролью director.
import { ref, computed } from 'vue';
import { login, register, authState } from '@/api/authClient';
import ThemeToggle from '@/components/ui/ThemeToggle.vue';
const emit = defineEmits(['session']);   // готовая сессия → App скрывает gate

const mode = ref('login');            // login | register
const user = ref('');
const name = ref('');
const pass = ref('');
const pass2 = ref('');
const busy = ref(false);
const error = ref('');
const info = ref('');

const firstRun = computed(() => authState.required && !authState.hasUsers);

function switchMode(m) { mode.value = m; error.value = ''; info.value = ''; }

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
      emit('session', res);
    } else {
      const res = await register(user.value.trim(), pass.value, name.value.trim());
      if (res.firstAccount) {
        emit('session', res);
        return;
      }
      // зарегистрировались → сразу входим под этим же логином/паролем:
      // получаем pending-токен и можем заполнить профиль до подтверждения
      const lg = await login(res.login || user.value.trim(), pass.value);
      if (lg.token) {
        emit('session', lg);
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

</script>

<template>
  <div class="gate">
    <div class="gate-theme"><ThemeToggle /></div>
    <form class="gate-card" @submit.prevent="submit">
      <div class="gate-brand"><span class="brand-mark">🌱</span><strong>BIOTORF BUSINESS OS</strong></div>

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
    </form>
  </div>
</template>

<style scoped>
.gate{position:relative;min-height:100vh;display:grid;place-items:center;background:#0f2b21;padding:68px 20px 20px}
.gate-theme{position:absolute;inset-block-start:12px;inset-inline-end:12px}
.gate-card{width:min(400px,100%);background:var(--panel);border-radius:16px;padding:28px 26px;box-shadow:var(--elevation);display:flex;flex-direction:column;gap:12px}
.gate-brand{display:flex;align-items:center;gap:10px;margin-bottom:4px}
.gate-brand strong{letter-spacing:1.5px;font-size:14px;color:var(--accent-ink)}
.gate-card h2{font-size:19px;margin-bottom:2px}
.gate-note{font-size:12px;color:var(--warning-ink);background:var(--warning-soft);border:1px solid var(--warning-border);border-radius:9px;padding:9px 11px;margin:0}
.gate-note.err{color:var(--danger-ink);background:var(--danger-soft);border-color:var(--danger-border)}
.gate-note.ok{color:var(--accent-ink);background:var(--accent-soft);border-color:var(--accent-border)}
.gate-card .btn.primary{margin-top:6px}
.gate-switch{font-size:12px}
</style>
