<script setup>
import { computed } from 'vue';
import { useFormatters } from '@/composables/useFormatters';

const props = defineProps({ status: { type: String, default: '' } });
const { pillColor } = useFormatters();
const color = computed(() => pillColor(props.status));
</script>

<template>
  <span class="pill" :class="color">{{ status }}</span>
</template>