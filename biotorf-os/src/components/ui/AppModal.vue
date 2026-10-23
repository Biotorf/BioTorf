<script setup>
import { useUiStore } from '@/stores/ui';
const ui = useUiStore();
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.modal" class="modal-backdrop" @click.self="ui.closeModal()">
      <div class="modal" role="dialog" aria-modal="true" :aria-label="ui.modal.title">
        <div class="modal-title">
          <h2>{{ ui.modal.title }}</h2>
          <button class="btn ghost slim" @click="ui.closeModal()">✕</button>
        </div>
        <div class="modal-body">
          <component :is="ui.modal.component" v-bind="ui.modal.props" />
        </div>
      </div>
    </div>
  </Teleport>
</template>