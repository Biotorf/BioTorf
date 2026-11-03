<script setup>
const props = defineProps({
  variant: { type: String, default: 'primary' }, // primary | ghost | slim | danger | success | outline
  slim: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  icon: { type: String, default: '' },            // эмодзи/SVG-символ слева от текста
});
defineEmits(['click']);
</script>

<template>
  <button
    class="btn btn-modern"
    :class="[props.variant, { slim: props.slim }]"
    :disabled="props.disabled"
    @click="$emit('click', $event)"
  >
    <span v-if="props.icon" class="btn-ico">{{ props.icon }}</span>
    <span class="btn-label"><slot /></span>
    <span class="btn-ripple" aria-hidden="true"></span>
  </button>
</template>

<style scoped>
.btn-modern {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-radius: 11px;
  font-weight: 650;
  letter-spacing: .1px;
  position: relative;
  overflow: hidden;
  isolation: isolate;
  transition: transform .16s cubic-bezier(.2,.8,.3,1), box-shadow .16s ease, background .16s ease, border-color .16s ease, color .16s ease;
}
.btn-ico { font-size: 14px; line-height: 1; transform: translateY(.5px); }
.btn-label { white-space: nowrap; }

/* блик по диагонали при наведении */
.btn-ripple {
  position: absolute; inset: 0; z-index: -1;
  background: linear-gradient(105deg, transparent 40%, rgba(255,255,255,.35) 50%, transparent 60%);
  transform: translateX(-120%);
  transition: transform .5s ease;
  pointer-events: none;
}
.btn-modern:not(:disabled):hover .btn-ripple { transform: translateX(120%); }

.btn-modern:not(:disabled):hover { transform: translateY(-1.5px); }
.btn-modern:not(:disabled):active { transform: translateY(0) scale(.965); }
.btn-modern:focus-visible { outline: 2px solid #29bb5b; outline-offset: 2px; }

/* варианты */
.btn-modern.danger {
  background: #fff; border: 1px solid #f0c3bd; color: #c14e43;
}
.btn-modern.danger:not(:disabled):hover {
  background: linear-gradient(135deg,#e86a5f,#cf4d43); border-color: #cf4d43; color: #fff;
  box-shadow: 0 5px 14px rgba(207,77,67,.3);
}
.btn-modern.success {
  background: linear-gradient(135deg,#3ecf7a,#22a75c); border-color: #22a75c; color: #fff;
  box-shadow: 0 2px 8px rgba(34,167,92,.28);
}
.btn-modern.success:not(:disabled):hover { box-shadow: 0 6px 16px rgba(34,167,92,.38); }
.btn-modern.outline {
  background: transparent; border: 1.5px solid #bcdcc8; color: #1c7a56;
}
.btn-modern.outline:not(:disabled):hover {
  background: #eafaf0; border-color: #29bb5b;
  box-shadow: 0 4px 12px rgba(41,187,91,.15);
}
@media (prefers-reduced-motion: reduce) {
  .btn-modern, .btn-ripple { transition: none; }
  .btn-modern:not(:disabled):hover { transform: none; }
}
</style>