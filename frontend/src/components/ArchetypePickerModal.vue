<template>
  <div class="modal" :hidden="!visible">
    <div class="modal-backdrop" @click="$emit('close')"></div>
    <div class="modal-content modal-large">
      <button class="modal-close" @click="$emit('close')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <h2>Select Archetypes</h2>

      <div class="arch-picker-toolbar">
        <input
          v-model="search"
          type="text"
          placeholder="Search archetypes..."
          class="arch-picker-search"
          ref="searchInput"
        >
        <select v-model="sortMode" class="arch-picker-sort">
          <option value="count_desc">Most cards first</option>
          <option value="count_asc">Fewest cards first</option>
          <option value="name_asc">Name A-Z</option>
          <option value="name_desc">Name Z-A</option>
        </select>
      </div>

      <div class="arch-picker-actions-bar">
        <span class="text-secondary">{{ selected.size }} selected</span>
        <button class="btn-secondary btn-sm" @click="selectAll">Select all visible</button>
        <button class="btn-secondary btn-sm" @click="deselectAll">Deselect all</button>
      </div>

      <div class="arch-picker-list">
        <label
          v-for="item in sortedItems"
          :key="item.name"
          class="arch-picker-item"
          :class="{ disabled: item.count === 0 }"
        >
          <input
            type="checkbox"
            :checked="selected.has(item.name)"
            :disabled="item.count === 0"
            @change="toggle(item.name)"
          >
          <span class="arch-picker-name">{{ item.name }}</span>
          <span class="arch-picker-count" :class="{ empty: item.count === 0 }">{{ item.count }}</span>
        </label>
        <p v-if="sortedItems.length === 0" class="text-secondary" style="text-align:center;padding:24px 0">
          No archetypes found
        </p>
      </div>

      <div class="modal-actions">
        <button class="btn-secondary" @click="$emit('close')">Cancel</button>
        <button class="btn-primary" @click="confirm">Apply</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  archetypes: { type: Array, default: () => [] },
  availability: { type: Object, default: () => ({}) },
  modelValue: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'close'])

const search = ref('')
const sortMode = ref('count_desc')
const searchInput = ref(null)
const selected = ref(new Set(props.modelValue))

watch(() => props.visible, (v) => {
  if (v) {
    selected.value = new Set(props.modelValue)
    search.value = ''
    nextTick(() => searchInput.value?.focus())
  }
})

watch(() => props.modelValue, (v) => {
  selected.value = new Set(v)
})

const hasAvailability = computed(() => Object.keys(props.availability).length > 0)

const filteredItems = computed(() => {
  const q = search.value.toLowerCase()
  return props.archetypes
    .map(name => ({
      name,
      count: hasAvailability.value ? (props.availability[name] ?? 0) : null,
    }))
    .filter(item => !q || item.name.toLowerCase().includes(q))
})

const sortedItems = computed(() => {
  const items = [...filteredItems.value]
  switch (sortMode.value) {
    case 'count_desc':
      return items.sort((a, b) => (b.count ?? 0) - (a.count ?? 0) || a.name.localeCompare(b.name))
    case 'count_asc':
      return items.sort((a, b) => (a.count ?? 0) - (b.count ?? 0) || a.name.localeCompare(b.name))
    case 'name_asc':
      return items.sort((a, b) => a.name.localeCompare(b.name))
    case 'name_desc':
      return items.sort((a, b) => b.name.localeCompare(a.name))
    default:
      return items
  }
})

function toggle(name) {
  const s = new Set(selected.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  selected.value = s
}

function selectAll() {
  const s = new Set(selected.value)
  for (const item of sortedItems.value) {
    if (item.count !== 0) s.add(item.name)
  }
  selected.value = s
}

function deselectAll() {
  selected.value = new Set()
}

function confirm() {
  emit('update:modelValue', [...selected.value])
  emit('close')
}
</script>
