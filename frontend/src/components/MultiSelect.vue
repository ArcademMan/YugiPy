<template>
  <div class="multi-select" ref="root">
    <button type="button" class="multi-select-trigger" @click="open = !open">
      <span class="multi-select-label">{{ displayLabel }}</span>
      <span class="multi-select-arrow">&#9662;</span>
    </button>
    <div v-if="open" class="multi-select-dropdown">
      <template v-for="opt in visibleOptions" :key="opt.value">
        <label class="multi-select-option" :class="{ disabled: opt.disabled }">
          <input
            type="checkbox"
            :value="opt.value"
            v-model="selected"
            :disabled="opt.disabled"
            @change="emitChange"
          >
          <span>{{ opt.label }}</span>
          <span v-if="opt.count != null" class="multi-select-count">({{ opt.count }})</span>
        </label>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  options: { type: Array, required: true },
  modelValue: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'All' },
  hideDisabled: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const root = ref(null)
const selected = ref([...props.modelValue])

watch(() => props.modelValue, (v) => { selected.value = [...v] })

const visibleOptions = computed(() => {
  if (!props.hideDisabled) return props.options
  return props.options.filter(o => !o.disabled || selected.value.includes(o.value))
})

const displayLabel = computed(() => {
  if (selected.value.length === 0) return props.placeholder
  if (selected.value.length <= 2) {
    return selected.value.map(v => props.options.find(o => o.value === v)?.label || v).join(', ')
  }
  return `${selected.value.length} selected`
})

function emitChange() {
  emit('update:modelValue', [...selected.value])
}

function onClickOutside(e) {
  if (root.value && !root.value.contains(e.target)) open.value = false
}

onMounted(() => document.addEventListener('click', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', onClickOutside))
</script>
