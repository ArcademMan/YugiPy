<template>
  <TransitionGroup name="toast" tag="div" class="toast-container">
    <div v-for="toast in toasts" :key="toast.id" class="toast">
      {{ toast.message }}
    </div>
  </TransitionGroup>
</template>

<script setup>
import { useToast } from '../composables/useToast.js'

const { toasts } = useToast()
</script>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 90px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  pointer-events: none;
}

.toast-enter-active {
  animation: toastIn 0.3s ease;
}
.toast-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.toast-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
