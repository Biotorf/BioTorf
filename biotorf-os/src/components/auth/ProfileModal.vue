<script setup>
// Модалка «Профиль сотрудника»: данные заполняет сам сотрудник.
import { ref, onMounted } from 'vue';
import { getMyProfile, saveMyProfile, changeMyPassword } from '@/api/authClient';
import { useUiStore } from '@/stores/ui';

const ui = useUiStore();
const loading = ref(true);
const saving = ref(false);
const error = ref('');
const saved = ref(false);
const p = ref({ name: '', position: '', phone: '', email: '', note: '' });
const role = ref(''); const roleName = ref(''); const loginName = ref('');

// смена пароля
const showPass = ref(false);
const oldPass = ref(''); const newPass = ref(''); const newPass2 = ref('');
const passMsg = ref('');

onMounted(async () => {
  try {
    const me = await getMyProfile();
    p.value = { name: me.name || '', position: me.position || '', phone: me.phone || '', email: me.email || '', note: me.note || '' };
    role.value = me.role; roleName.value = me.roleName || ''; loginName.value = me.login || ui.login || '';
  } catch (e) { error.value = e.message || 'Не удалось загрузить профиль'; }
  finally { loading.value = false; }
});

async function save() {
  saving.value = true; error.value = ''; saved.value = false;
  try {
    const res = await saveMyProfile(p.value);
    // обновляем имя в сессии, чтобы мини-профиль показал актуальные данные
    if (res && res.name) {
      const u = ui.user || {};
      localStorage.setItem('biotorf.auth.user', JSON.stringify({ ...u, name: res.name }));
      ui.applySession({ ...u, name: res.name });
    }
    saved.value = true;
  } catch (e) { error.value = e.message || 'Сервер недоступен'; }
  finally { saving.value = false; }
}

async function changePass() {
  passMsg.value = '';
  if (newPass.value !== newPass2.value) { passMsg.value = 'Новые пароли не совпадают'; return; }
  try {
    await changeMyPassword(oldPass.value, newPass.value);
    passMsg.value = 'Пароль изменён — войдите заново.';
    setTimeout(() => ui.logoutEverywhere?.(), 1500);
  } catch (e) { passMsg.value = e.message || 'Ошибка'; }
}
</script>

<template>
  <div class="profile">
    <div v-if="loading" class="muted">Загрузка…</div>
    <template v-else>
      <div class="head">
        <div class="avatar">{{ (p.name || loginName || '?')[0].toUpperCase() }}</div>
        <div>
          <b>{{ p.name || loginName }}</b>
          <div class="muted">{{ roleName }} · логин {{ loginName }}</div>
        </div>
      </div>

      <label class="fl">Имя<input v-model="p.name" class="input" placeholder="Иван Петров" /></label>
      <label class="fl">Должность<input v-model="p.position" class="input" placeholder="Агроном-консультант" /></label>
      <label class="fl">Телефон<input v-model="p.phone" class="input" placeholder="+7 900 000-00-00" /></label>
      <label class="fl">E-mail<input v-model="p.email" class="input" placeholder="name@biotorf.ru" /></label>
      <label class="fl">О себе / заметки<textarea v-model="p.note" class="input" rows="3" placeholder="Регион, специализация…"></textarea></label>

      <p v-if="error" class="msg err">{{ error }}</p>
      <p v-if="saved" class="msg ok">Профиль сохранён ✓</p>
      <p v-if="role === 'pending'" class="msg wait">
        ⏳ Учётная запись ожидает подтверждения роли генеральным директором.
        Данные профиля видны директору в разделе «Сотрудники» — после выдачи роли
        откроется доступ к системе.
      </p>

      <div class="row">
        <button class="btn primary" :disabled="saving" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
        <button class="btn ghost slim" @click="showPass = !showPass">{{ showPass ? 'Отменить' : 'Сменить пароль' }}</button>
      </div>

      <div v-if="showPass" class="passbox">
        <label class="fl">Текущий пароль<input v-model="oldPass" type="password" class="input" autocomplete="current-password" /></label>
        <label class="fl">Новый пароль (от 8 символов)<input v-model="newPass" type="password" class="input" autocomplete="new-password" /></label>
        <label class="fl">Повторите новый<input v-model="newPass2" type="password" class="input" autocomplete="new-password" /></label>
        <p v-if="passMsg" class="msg">{{ passMsg }}</p>
        <button class="btn primary slim" @click="changePass">Сменить пароль</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.profile{display:flex;flex-direction:column;gap:10px;min-width:300px}
.head{display:flex;align-items:center;gap:12px;margin-bottom:4px}
.avatar{width:44px;height:44px;border-radius:50%;background:#214f37;color:#fff;display:grid;place-items:center;font-size:19px;font-weight:700}
.fl{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#5b6b62}
.muted{color:#8aa398;font-size:12px}
.msg{font-size:12px;margin:0;padding:7px 10px;border-radius:8px;background:#fffbec;border:1px solid #e7ddbf;color:#7a6840}
.msg.err{background:#ffedea;border-color:#f0cfc9;color:#b94337}
.msg.ok{background:#e5f5ee;border-color:#cfe9db;color:#218468}
.msg.wait{background:#fff7e0;border-color:#ead9a8;color:#8a6d1b}
.row{display:flex;gap:8px;align-items:center;margin-top:4px}
.passbox{display:flex;flex-direction:column;gap:8px;border-top:1px dashed #d8e2dc;padding-top:10px}
</style>
