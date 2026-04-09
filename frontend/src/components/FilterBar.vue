<template>
  <div class="filter-bar">
    <select v-model="sortBy" @change="onSortChange">
      <option value="price-desc">Price &#x2193;</option>
      <option value="price-asc">Price &#x2191;</option>
      <option value="name-asc">Name A-Z</option>
      <option value="name-desc">Name Z-A</option>
      <option value="type">Type</option>
      <option value="qty-desc">Quantity &#x2193;</option>
      <option value="id-desc">Newest</option>
      <option value="id-asc">Oldest</option>
    </select>
    <select v-model="filters.rarity" @change="onServerFilterChange">
      <option value="">All rarities</option>
      <option v-for="r in availableRarities" :key="r" :value="r">{{ r }}</option>
    </select>
    <select v-model="filters.condition" @change="onServerFilterChange">
      <option value="">All conditions</option>
      <option v-for="c in CONDITION_OPTIONS" :key="c.value" :value="c.value">{{ c.label }}</option>
    </select>
    <select v-model="filters.lang" @change="onServerFilterChange">
      <option value="">All languages</option>
      <option v-for="l in LANG_OPTIONS" :key="l.value" :value="l.value">{{ l.label }}</option>
    </select>
    <select v-model="filters.archetype">
      <option value="">All archetypes</option>
      <option v-for="a in availableArchetypes" :key="a" :value="a">{{ a }}</option>
    </select>
    <select v-model="filters.set">
      <option value="">All sets</option>
      <option v-for="s in availableSets" :key="s" :value="s">{{ s }}</option>
    </select>
    <select v-model="filters.type">
      <option value="">All types</option>
      <option v-for="t in availableTypes" :key="t" :value="t">{{ t }}</option>
    </select>
    <select v-model="filters.level">
      <option value="">All levels</option>
      <option v-for="l in availableLevels" :key="l" :value="l">{{ l }}</option>
    </select>
    <select v-model="filters.location">
      <option value="">All locations</option>
      <option v-for="l in availableLocations" :key="l" :value="l">{{ l }}</option>
    </select>
  </div>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import { CONDITION_OPTIONS, LANG_OPTIONS, TYPE_GROUP, TYPE_ORDER } from '../utils/constants.js'

const props = defineProps({
  cards: { type: Array, default: () => [] }
})

const emit = defineEmits(['server-filter-change', 'update:filters'])

const sortBy = defineModel('sort', { default: localStorage.getItem('yugipy_collection_sort') || 'price-desc' })

const filters = reactive({
  rarity: '',
  condition: '',
  lang: '',
  archetype: '',
  set: '',
  type: '',
  level: '',
  location: ''
})

function onSortChange() {
  localStorage.setItem('yugipy_collection_sort', sortBy.value)
}

function onServerFilterChange() {
  emit('server-filter-change')
}

// Available filter options from loaded cards
const availableRarities = computed(() => [...new Set(props.cards.map(c => c.rarity))].sort())
const availableArchetypes = computed(() => [...new Set(props.cards.map(c => c.archetype).filter(Boolean))].sort())
const availableSets = computed(() => [...new Set(props.cards.map(c => c.set_code ? c.set_code.split('-')[0] : '').filter(Boolean))].sort())
const availableTypes = computed(() => {
  const types = [...new Set(props.cards.map(c => TYPE_GROUP[c.type] || c.type).filter(Boolean))]
  return types.sort((a, b) => (TYPE_ORDER[a] ?? 99) - (TYPE_ORDER[b] ?? 99))
})
const availableLevels = computed(() => [...new Set(props.cards.map(c => c.level).filter(l => l != null))].sort((a, b) => a - b).map(String))
const availableLocations = computed(() => [...new Set(props.cards.flatMap(c => c.location || []))].sort())

// Emit filters on any change
watch(filters, () => emit('update:filters', { ...filters }), { deep: true })

defineExpose({ filters, sortBy })
</script>
