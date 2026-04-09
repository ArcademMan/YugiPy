<template>
  <section>
    <div class="page-header">
      <h1>My Collection</h1>
      <div class="stats-badge">{{ statsBadge }}</div>
    </div>

    <div class="search-bar">
      <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input type="text" v-model="searchQuery" placeholder="Filter by name or set code...">
    </div>

    <FilterBar
      ref="filterRef"
      :cards="store.allCards"
      v-model:sort="sortBy"
      @server-filter-change="loadCards"
      @update:filters="onFiltersUpdate"
    />

    <CardGrid :cards="sortedCards" @card-click="openModal" />

    <button class="fab" title="Add card manually" @click="searchModalVisible = true">+</button>

    <div class="empty-state" v-if="sortedCards.length === 0 && !loading">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><rect x="2" y="3" width="20" height="18" rx="2"/><path d="M8 7h8M8 11h5"/></svg>
      <h3>No cards</h3>
      <p>Use the scanner to add your cards to the collection</p>
    </div>

    <CardModal
      :visible="cardModalVisible"
      :card="modalCard"
      :cardId="modalCardId"
      @close="onCardModalClose"
      @updated="loadCards"
      @deleted="onCardDeleted"
      @split="onSplitRequest"
    />

    <SplitModal
      :visible="splitModalVisible"
      :card="splitCard"
      @close="splitModalVisible = false"
      @split="onSplitDone"
    />

    <AddCardModal
      :visible="addModalVisible"
      :cardData="addCardData"
      :sets="addCardSets"
      @close="addModalVisible = false"
      @added="loadCards"
    />

    <SearchModal
      :visible="searchModalVisible"
      @close="searchModalVisible = false"
      @add="onSearchAdd"
    />
  </section>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useCollectionStore } from '../stores/collection.js'
import { useSettingsStore } from '../stores/settings.js'
import { getDisplayPrice } from '../utils/price.js'
import { TYPE_GROUP, TYPE_ORDER } from '../utils/constants.js'
import CardGrid from '../components/CardGrid.vue'
import FilterBar from '../components/FilterBar.vue'
import CardModal from '../components/CardModal.vue'
import SplitModal from '../components/SplitModal.vue'
import AddCardModal from '../components/AddCardModal.vue'
import SearchModal from '../components/SearchModal.vue'

const store = useCollectionStore()
const settings = useSettingsStore()

const loading = ref(false)
const searchQuery = ref('')
const sortBy = ref(localStorage.getItem('yugipy_collection_sort') || 'price-desc')
const filterRef = ref(null)
const localFilters = ref({})

// Modal state
const cardModalVisible = ref(false)
const modalCard = ref(null)
const modalCardId = ref(null)
const splitModalVisible = ref(false)
const splitCard = ref(null)
const addModalVisible = ref(false)
const addCardData = ref(null)
const addCardSets = ref([])
const searchModalVisible = ref(false)

async function loadCards() {
  loading.value = true
  const params = {}
  const f = filterRef.value?.filters
  if (f?.rarity) params.rarity = f.rarity
  if (f?.condition) params.condition = f.condition
  if (f?.lang) params.lang = f.lang
  await store.loadCollection(params)
  loading.value = false
}

function onFiltersUpdate(filters) {
  localFilters.value = filters
}

// Filter and sort cards
const filteredCards = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  const f = localFilters.value
  return store.allCards.filter(c => {
    if (q && !c.name.toLowerCase().includes(q) && !(c.set_code && c.set_code.toLowerCase().includes(q))) return false
    if (f.archetype && c.archetype !== f.archetype) return false
    if (f.set && !(c.set_code || '').startsWith(f.set + '-') && !(c.set_code || '').startsWith(f.set)) return false
    if (f.type && (TYPE_GROUP[c.type] || c.type) !== f.type) return false
    if (f.level && c.level !== parseInt(f.level)) return false
    if (f.location && !(c.location || []).includes(f.location)) return false
    return true
  })
})

const sortedCards = computed(() => {
  const cards = [...filteredCards.value]
  const mode = settings.priceDisplayMode
  switch (sortBy.value) {
    case 'name-asc': cards.sort((a, b) => a.name.localeCompare(b.name)); break
    case 'name-desc': cards.sort((a, b) => b.name.localeCompare(a.name)); break
    case 'price-desc': cards.sort((a, b) => (getDisplayPrice(b, mode).price || 0) - (getDisplayPrice(a, mode).price || 0)); break
    case 'price-asc': cards.sort((a, b) => (getDisplayPrice(a, mode).price || 0) - (getDisplayPrice(b, mode).price || 0)); break
    case 'qty-desc': cards.sort((a, b) => b.quantity - a.quantity); break
    case 'type': cards.sort((a, b) => {
      const aO = TYPE_ORDER[TYPE_GROUP[a.type] || a.type] ?? 99
      const bO = TYPE_ORDER[TYPE_GROUP[b.type] || b.type] ?? 99
      return aO - bO || (b.level ?? 0) - (a.level ?? 0) || a.name.localeCompare(b.name)
    }); break
    case 'id-desc': cards.sort((a, b) => b.id - a.id); break
    case 'id-asc': cards.sort((a, b) => a.id - b.id); break
  }
  return cards
})

const statsBadge = computed(() => {
  const cards = sortedCards.value
  if (!cards.length) return ''
  const total = cards.reduce((s, c) => s + c.quantity, 0)
  const value = cards.reduce((s, c) => s + (getDisplayPrice(c, settings.priceDisplayMode).price || 0) * c.quantity, 0)
  return `${cards.length} unique cards \u00B7 ${total} total \u00B7 ${value.toFixed(2)}\u20AC`
})

// Modal handlers
function openModal(id) {
  const card = store.allCards.find(c => c.id === id)
  if (!card) return
  modalCard.value = card
  modalCardId.value = id
  cardModalVisible.value = true
}

function onCardModalClose() {
  cardModalVisible.value = false
  loadCards()
}

function onCardDeleted() {
  cardModalVisible.value = false
  loadCards()
}

function onSplitRequest(card) {
  splitCard.value = card
  splitModalVisible.value = true
}

function onSplitDone() {
  splitModalVisible.value = false
  cardModalVisible.value = false
  loadCards()
}

function onSearchAdd(cardData, sets) {
  addCardData.value = cardData
  addCardSets.value = sets
  searchModalVisible.value = false
  addModalVisible.value = true
}

// Initial load
loadCards()
</script>
