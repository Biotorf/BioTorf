<script setup>
defineProps({
  variant: { type: String, default: 'primary' }, // primary | ghost | slim
  slim: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
});
defineEmits(['click']);
</script>

<template>
  <button
    class="btn"
    :class="[variant, { slim }]"
    :disabled="disabled"
    @click="$emit('click', $event)"
  >
    <slot />
  </button>
</template>