<script setup>
import { useUiStore } from '@/stores/ui';
import { useDbStore } from '@/stores/db';
import { usePermissions } from '@/composables/usePermissions';
import MiniProfile from '@/components/auth/MiniProfile.vue';
import ManualLink from '@/components/ui/ManualLink.vue';
import { usePwaInstall } from '@/composables/usePwaInstall';

const ui = useUiStore();
const db = useDbStore();
const { ROLES } = usePermissions();
const { showInstallButton, installHint, promptInstall } = usePwaInstall();
</script>

<template>
  <div class="topbar">
    <div class="search">
      <span>⌕</span>
      <input
        v-model="ui.search"
        type="search"
        placeholder="Поиск по текущему разделу…"
      />
    </div>
    <div class="topright">
      <button class="toolbar-icon" @click="ui.go('comms')" title="Коммуникации: звонки и сообщения">
        ☎<i v-if="db.comms.filter((c) => !c.read).length">{{ db.comms.filter((c) => !c.read).length }}</i>
      </button>
      <button class="toolbar-icon" @click="ui.go('notifications')" title="Уведомления">
        ♢<i>{{ db.lateTasks.length }}</i>
      </button>
      <button class="toolbar-icon" @click="ui.go('calendar')" title="Календарь">▦</button>
      <button
        v-if="showInstallButton"
        class="install-btn"
        @click="promptInstall"
        title="Установить BIOTORF как приложение на компьютер"
      >⤓ Установить</button>
      <span v-if="installHint" class="install-toast" title="Через 12 секунд подсказка скроется">✅ Приложение установлено — ярлык в «Пуск» и на рабочем столе. Нужен файл .lnk? Меню браузера (⋮) → «Сохранить и поделиться» → «Создать ярлык…»</span>
      <ManualLink />
      <!-- мини-профиль: аватар с выпадающим меню (Профиль / Выйти) -->
      <MiniProfile />
    </div>
  </div>
</template>