<script setup>
// Выпадающий мини-профиль в топбаре: аватар → меню (Профиль / Выход).
// «Профиль» открывает модалку ProfileModal, где сотрудник заполняет свои данные.
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useUiStore } from '@/stores/ui';
import { logout, authState } from '@/api/authClient';

const ui = useUiStore();
const open = ref(false);
const btn = ref(null);

const fullName = computed(() => ui.name || authState.user?.name || ui.login || 'Сотрудник');
const initial = computed(() => (String(fullName.value).trim()[0] || '?').toUpperCase());
const subline = computed(() => authState.user?.login || ui.login || '');
const roleLabel = computed(() => ({
  director: 'Генеральный директор', pending: 'Ожидает подтверждения',
  sales: 'Продажи', agronomist: 'Агроном', logistics: 'Логистика',
  production: 'Производство', finance: 'Финансы',
}[ui.role] || ui.role || ''));

function toggle() { open.value = !open.value; }
function close(ev) {
  if (btn.value && !btn.value.contains(ev.target)) open.value = false;
}
onMounted(() => document.addEventListener('click', close));
onBeforeUnmount(() => document.removeEventListener('click', close));

function openProfile() {
  open.value = false;
  ui.openMyProfile();
}
function doLogout() {
  open.value = false;
  logout(); ui.clearSession();
  // AuthGate в App.vue подхватит отсутствие токена и покажет экран входа
}
</script>

<template>
  <div class="mini" ref="btn">
    <button class="avatar-btn" :class="{ active: open }" @click.stop="toggle"
            :title="`Мини-профиль · ${fullName}`">
      <span class="avatar">{{ initial }}</span>
      <span class="who">
        <b>{{ fullName }}</b>
        <i>{{ roleLabel }}</i>
      </span>
      <span class="caret">▾</span>
    </button>

    <div v-if="open" class="menu" @click.stop>
      <div class="menu-head">
        <span class="avatar big">{{ initial }}</span>
        <div>
          <b>{{ fullName }}</b>
          <small>{{ subline }}{{ roleLabel ? ` · ${roleLabel}` : '' }}</small>
        </div>
      </div>
      <button class="item" @click="openProfile">👤 Профиль сотрудника</button>
      <button class="item danger" @click="doLogout">↩ Выйти</button>
    </div>
  </div>
</template>

<style scoped>
.mini{position:relative}
.avatar-btn{display:flex;align-items:center;gap:8px;background:none;border:1px solid transparent;
  border-radius:10px;padding:4px 8px;cursor:pointer;font:inherit;color:inherit}
.avatar-btn:hover,.avatar-btn.active{background:#f2efe7;border-color:#e3ddcd}
.avatar{width:28px;height:28px;border-radius:50%;background:#214f37;color:#fff;
  display:grid;place-items:center;font-size:13px;font-weight:700;flex:none}
.avatar.big{width:38px;height:38px;font-size:16px}
.who{display:flex;flex-direction:column;align-items:flex-start;line-height:1.15;max-width:140px}
.who b{font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:140px}
.who i{font-style:normal;font-size:10.5px;color:#8a8271}
.caret{font-size:10px;color:#8a8271}
.menu{position:absolute;right:0;top:calc(100% + 6px);min-width:220px;background:#fff;
  border:1px solid #e3ddcd;border-radius:12px;box-shadow:0 14px 40px rgba(30,25,10,.16);
  padding:8px;display:flex;flex-direction:column;gap:4px;z-index:60}
.menu-head{display:flex;align-items:center;gap:10px;padding:6px 8px 8px;border-bottom:1px solid #eee7d8;margin-bottom:4px}
.menu-head b{display:block;font-size:13px}
.menu-head small{color:#8a8271;font-size:11px}
.item{text-align:left;background:none;border:0;border-radius:8px;padding:8px 10px;cursor:pointer;font:inherit;font-size:13px}
.item:hover{background:#f5f2ea}
.item.danger{color:#b94337}
.item.danger:hover{background:#ffedea}
</style>
