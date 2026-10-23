<script setup>
defineProps({ label: String, value: [String, Number], foot: String });
</script>

<template>
  <div class="stat">
    <div class="label">{{ label }}</div>
    <div class="val mono">{{ value }}</div>
    <div v-if="foot" class="foot">{{ foot }}</div>
  </div>
</template>