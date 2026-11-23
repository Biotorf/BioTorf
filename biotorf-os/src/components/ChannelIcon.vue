<script setup>
import { computed } from 'vue';
import telegram from '@/assets/channels/telegram.svg';
import whatsapp from '@/assets/channels/whatsapp.svg';
import instagram from '@/assets/channels/instagram.svg';
import facebook from '@/assets/channels/facebook.svg';
import vk from '@/assets/channels/vk.svg';
import ok from '@/assets/channels/ok.svg';
import avito from '@/assets/channels/avito.png';
import youdo from '@/assets/channels/youdo.png';

// Telegram, Avito and YouDo supply their own marks at telegram.org/img/t_logo.svg,
// career.avito.com/favicon.ico and youdo.com/favicon.ico. The other brand glyphs
// come from Simple Icons v15.0.0 (CC0, https://github.com/simple-icons/simple-icons).
const assets = new Map(Object.entries({ telegram, whatsapp, instagram, facebook, vk, ok, avito, youdo }));
const aliases = new Map(Object.entries({
  tg: 'telegram', wa: 'whatsapp', phone: 'call', telephony: 'call', mail: 'email',
  vkontakte: 'vk', odnoklassniki: 'ok',
}));

const props = defineProps({
  kind: { type: String, default: '' },
  size: { type: [Number, String], default: 20 },
  fallback: { type: String, default: '' },
});

const channel = computed(() => {
  const kind = String(props.kind ?? '').trim().toLowerCase();
  return aliases.get(kind) ?? kind;
});
const source = computed(() => assets.get(channel.value));
const customMark = computed(() => ['all', 'call', 'email'].includes(channel.value) ? '' : props.fallback.trim());
</script>

<template>
  <span class="channel-icon" :data-channel="channel" :style="{ '--channel-icon-size': `${size}px` }" aria-hidden="true">
    <img v-if="source" :src="source" alt="" draggable="false" />
    <span v-else-if="customMark" class="custom-mark">{{ customMark }}</span>
    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" focusable="false">
      <path v-if="channel === 'call'" d="M21 16.8v2.4a2 2 0 0 1-2.2 2 17.8 17.8 0 0 1-7.8-2.8 17.3 17.3 0 0 1-5.4-5.4 17.8 17.8 0 0 1-2.8-7.9A2 2 0 0 1 4.8 3h2.4a2 2 0 0 1 2 1.7l.5 2.6a2 2 0 0 1-.6 2.1l-1 1a13.9 13.9 0 0 0 5.4 5.4l1-1a2 2 0 0 1 2.1-.6l2.7.5a2 2 0 0 1 1.7 2.1Z" />
      <g v-else-if="channel === 'email'">
        <rect x="3" y="5" width="18" height="14" rx="3" />
        <path d="m4 7 8 6 8-6" />
      </g>
      <path v-else-if="channel === 'all'" d="M3 6h18M3 12h18M3 18h18" />
      <path v-else d="M20 15a2 2 0 0 1-2 2H9l-5 4v-5.5a2 2 0 0 1-1-1.7V6a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2zM7 8h9m-9 4h6" />
    </svg>
  </span>
</template>

<style scoped>
.channel-icon {
  display: inline-grid;
  place-items: center;
  inline-size: var(--channel-icon-size);
  block-size: var(--channel-icon-size);
  flex: none;
  vertical-align: middle;
}
.channel-icon img,
.channel-icon svg {
  display: block;
  inline-size: 100%;
  block-size: 100%;
  object-fit: contain;
}
.custom-mark { max-width: 100%; overflow: hidden; font-size: var(--channel-icon-size); line-height: 1; white-space: nowrap; }
</style>
