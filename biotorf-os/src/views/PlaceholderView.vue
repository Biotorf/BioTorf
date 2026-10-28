<script setup>
defineProps({ title: { type: String, default: 'Раздел' } });
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>{{ title }}</h1>
        <div class="subtitle">Раздел в разработке.</div>
      </div>
    </div>
    <div class="empty">Содержимое раздела появится в следующей итерации.</div>
  </div>
</template>
