<script setup>
defineProps({ title: { type: String, default: 'Раздел' } });
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>{{ title }}</h1>
        <div class="subtitle">Раздел в разработке — переносится из демо v0.9 (BIOTORF_Business_OS_demo_v0.9.html).</div>
      </div>
    </div>
    <div class="empty">Содержимое раздела появится в следующей итерации.</div>
  </div>
</template>
