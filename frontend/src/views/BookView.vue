<template>
  <section>
    <div class="page-header">
      <div style="display:flex;align-items:center;gap:8px">
        <h1>Book</h1>
        <span class="stats-badge">{{ statsText }}</span>
      </div>
      <button class="btn-secondary" @click="settingsVisible = true" title="Settings">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
      </button>
    </div>

    <BookSettingsPanel
      :visible="settingsVisible"
      :availableSets="availableSets"
      :availableArchetypes="availableArchetypes"
      :initialPrefs="savedPrefs"
      :initialSortRules="savedSortRules"
      ref="settingsPanel"
      @change="onSettingsChange"
      @close="settingsVisible = false"
    />

    <div class="book-layout">
      <div class="book-main">
        <div class="book-spread" v-html="spreadHtml"></div>
        <div class="book-nav">
          <button class="btn-secondary" :disabled="currentSpread <= 0" @click="prevSpread">&larr;</button>
          <span>{{ pageNumText }}</span>
          <button class="btn-secondary" :disabled="currentSpread >= totalSpreads - 1" @click="nextSpread">&rarr;</button>
        </div>
      </div>
    </div>

    <CardModal
      :visible="cardModalVisible"
      :card="modalCard"
      :cardId="modalCardId"
      @close="onCardModalClose"
      @updated="loadData"
      @deleted="onCardDeleted"
      @split="onSplit"
    />
    <SplitModal
      :visible="splitModalVisible"
      :card="splitCard"
      @close="splitModalVisible = false"
      @split="onSplitDone"
    />
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useCollectionStore } from '../stores/collection.js'
import { useSettingsStore } from '../stores/settings.js'
import { RARITY_ORDER, TYPE_GROUP, TYPE_ORDER } from '../utils/constants.js'
import { cardImgUrl } from '../utils/images.js'
import { getDisplayPrice } from '../utils/price.js'
import BookSettingsPanel from '../components/BookSettingsPanel.vue'
import CardModal from '../components/CardModal.vue'
import SplitModal from '../components/SplitModal.vue'
import api from '../api.js'

const store = useCollectionStore()
const settings = useSettingsStore()

const settingsVisible = ref(false)
const settingsPanel = ref(null)
const currentSpread = ref(0)
const bookPages = ref([])

// Modal state
const cardModalVisible = ref(false)
const modalCard = ref(null)
const modalCardId = ref(null)
const splitModalVisible = ref(false)
const splitCard = ref(null)

// Saved prefs from settings
const savedPrefs = computed(() => settings.settings.bookPrefs || null)
const savedSortRules = computed(() => settings.settings.bookSortRules || null)

const availableSets = computed(() =>
  [...new Set(store.allCards.map(c => c.set_code ? c.set_code.split('-')[0] : '').filter(Boolean))].sort()
)

const availableArchetypes = computed(() =>
  [...new Set(store.allCards.map(c => c.archetype).filter(Boolean))].sort()
)

const statsText = computed(() => {
  const total = bookPages.value.reduce((s, p) => s + p.slots.filter(Boolean).length, 0)
  return `${total} cards \u00B7 ${bookPages.value.length} pages`
})

const totalSpreads = computed(() => Math.ceil(bookPages.value.length / 2))

const pageNumText = computed(() =>
  bookPages.value.length > 0 ? `${currentSpread.value + 1} / ${totalSpreads.value}` : 'No cards'
)

const spreadHtml = computed(() => {
  const leftIdx = currentSpread.value * 2
  const rightIdx = leftIdx + 1
  let html = ''
  if (leftIdx < bookPages.value.length) html += renderPage(bookPages.value[leftIdx])
  if (rightIdx < bookPages.value.length) html += renderPage(bookPages.value[rightIdx])
  return html
})

function renderPage(page) {
  const panel = settingsPanel.value
  const showPrices = panel?.prefs?.showPrices || false
  const gridSize = panel?.prefs?.gridSize || '3x3'
  const cols = parseInt(gridSize.split('x')[0])
  const header = page.group ? `<div class="book-page-header" title="${page.group}">${page.group}</div>` : ''
  const slots = page.slots.map(card => {
    if (!card) return '<div class="book-slot empty"></div>'
    const priceTag = showPrices ? (() => {
      const { price } = getDisplayPrice(card, settings.priceDisplayMode)
      return price ? `<span class="book-slot-price">${Number(price).toFixed(2)}\u20AC</span>` : ''
    })() : ''
    return `<div class="book-slot" data-id="${card.id}"><img src="${cardImgUrl(card.image_url)}" alt="${card.name}" title="${card.name}&#10;${card.set_code || ''} \u00B7 ${card.rarity} \u00B7 ${card.lang}" loading="lazy">${priceTag}</div>`
  }).join('')
  return `<div class="book-page">${header}<div class="book-page-grid" style="grid-template-columns:repeat(${cols},1fr)">${slots}</div></div>`
}

function buildBookPages(prefs, sortRulesArr) {
  const groupBy = prefs.groupBy || 'set'
  const newPagePerGroup = prefs.newPage !== false
  const gridSize = prefs.gridSize || '3x3'
  const [cols, rows] = gridSize.split('x').map(Number)
  const slotsPerPage = cols * rows
  const maxCopies = parseInt(prefs.maxCopies) || 0
  const filterLangs = prefs.filterLangs || []
  const filterConditions = prefs.filterConditions || []
  const filterArchetypes = prefs.filterArchetypes || []
  const filterSets = prefs.filterSets || []
  const minPrice = parseFloat(prefs.minPrice) || 0
  const copiesMode = prefs.copiesMode || 'entry'

  const langSet = filterLangs.length > 0 ? new Set(filterLangs) : null
  const condSet = filterConditions.length > 0 ? new Set(filterConditions) : null
  const archSet = filterArchetypes.length > 0 ? new Set(filterArchetypes) : null
  const setList = filterSets.length > 0 ? filterSets : null

  let filtered = store.allCards.filter(card => {
    if (langSet && !langSet.has(card.lang)) return false
    if (condSet && !condSet.has(card.condition)) return false
    if (archSet && !archSet.has(card.archetype)) return false
    if (setList && !setList.some(s => (card.set_code || '').startsWith(s))) return false
    if (minPrice > 0 && (getDisplayPrice(card, settings.priceDisplayMode).price || 0) < minPrice) return false
    return true
  })

  const expanded = []
  if (maxCopies > 0 && copiesMode === 'name') {
    const nameCount = new Map()
    for (const card of filtered) {
      const used = nameCount.get(card.name) || 0
      const remaining = maxCopies - used
      if (remaining <= 0) continue
      const copies = Math.min(card.quantity, remaining)
      nameCount.set(card.name, used + copies)
      for (let i = 0; i < copies; i++) expanded.push(card)
    }
  } else {
    for (const card of filtered) {
      const copies = maxCopies > 0 ? Math.min(card.quantity, maxCopies) : card.quantity
      for (let i = 0; i < copies; i++) expanded.push(card)
    }
  }

  const groups = new Map()
  for (const card of expanded) {
    let key
    switch (groupBy) {
      case 'set': key = card.set_code ? card.set_code.split('-')[0] : 'Other'; break
      case 'archetype': key = card.archetype || 'No archetype'; break
      case 'type': key = TYPE_GROUP[card.type] || card.type || 'Other'; break
      default: key = ''
    }
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(card)
  }

  const sortedKeys = [...groups.keys()].sort((a, b) => {
    if (a === 'Other' || a === 'No archetype') return 1
    if (b === 'Other' || b === 'No archetype') return -1
    if (groupBy === 'type') return (TYPE_ORDER[a] ?? 99) - (TYPE_ORDER[b] ?? 99)
    return a.localeCompare(b)
  })

  const mode = settings.priceDisplayMode
  const comparators = {
    rarity_desc: (a, b) => (RARITY_ORDER[b.rarity] ?? -1) - (RARITY_ORDER[a.rarity] ?? -1),
    rarity_asc: (a, b) => (RARITY_ORDER[a.rarity] ?? -1) - (RARITY_ORDER[b.rarity] ?? -1),
    name_asc: (a, b) => a.name.localeCompare(b.name),
    name_desc: (a, b) => b.name.localeCompare(a.name),
    type_asc: (a, b) => (TYPE_ORDER[TYPE_GROUP[a.type] || a.type] ?? 99) - (TYPE_ORDER[TYPE_GROUP[b.type] || b.type] ?? 99),
    type_desc: (a, b) => (TYPE_ORDER[TYPE_GROUP[b.type] || b.type] ?? 99) - (TYPE_ORDER[TYPE_GROUP[a.type] || a.type] ?? 99),
    type_creature_asc: (a, b) => {
      const ga = TYPE_GROUP[a.type] || a.type, gb = TYPE_GROUP[b.type] || b.type
      if (['Spell', 'Trap', 'Token'].includes(ga) || ['Spell', 'Trap', 'Token'].includes(gb)) return 0
      return (TYPE_ORDER[ga] ?? 99) - (TYPE_ORDER[gb] ?? 99)
    },
    type_creature_desc: (a, b) => {
      const ga = TYPE_GROUP[a.type] || a.type, gb = TYPE_GROUP[b.type] || b.type
      if (['Spell', 'Trap', 'Token'].includes(ga) || ['Spell', 'Trap', 'Token'].includes(gb)) return 0
      return (TYPE_ORDER[gb] ?? 99) - (TYPE_ORDER[ga] ?? 99)
    },
    level_desc: (a, b) => (b.level ?? 0) - (a.level ?? 0),
    level_asc: (a, b) => (a.level ?? 0) - (b.level ?? 0),
    set_code_asc: (a, b) => (a.set_code || '').localeCompare(b.set_code || ''),
    set_code_desc: (a, b) => (b.set_code || '').localeCompare(a.set_code || ''),
    price_desc: (a, b) => (getDisplayPrice(b, mode).price || 0) - (getDisplayPrice(a, mode).price || 0),
    price_asc: (a, b) => (getDisplayPrice(a, mode).price || 0) - (getDisplayPrice(b, mode).price || 0),
    archetype_asc: (a, b) => (a.archetype || '').localeCompare(b.archetype || ''),
    archetype_desc: (a, b) => (b.archetype || '').localeCompare(a.archetype || '')
  }
  const sortFn = (a, b) => {
    for (const rule of sortRulesArr) {
      const cmp = comparators[rule]
      if (!cmp) continue
      const result = cmp(a, b)
      if (result !== 0) return result
    }
    return 0
  }

  const pages = []
  if (groupBy === 'none' || !newPagePerGroup) {
    const allCards = []
    for (const key of sortedKeys) { groups.get(key).sort(sortFn); allCards.push(...groups.get(key)) }
    for (let i = 0; i < allCards.length; i += slotsPerPage) {
      pages.push({ group: null, slots: allCards.slice(i, i + slotsPerPage) })
    }
  } else {
    for (const key of sortedKeys) {
      const cards = groups.get(key).sort(sortFn)
      for (let i = 0; i < cards.length; i += slotsPerPage) {
        pages.push({ group: key, slots: cards.slice(i, i + slotsPerPage) })
      }
      const lastPage = pages[pages.length - 1]
      while (lastPage.slots.length < slotsPerPage) lastPage.slots.push(null)
    }
  }
  if (pages.length > 0) {
    const lastPage = pages[pages.length - 1]
    while (lastPage.slots.length < slotsPerPage) lastPage.slots.push(null)
  }
  return pages
}

function rebuildBook() {
  const panel = settingsPanel.value
  if (!panel) return
  bookPages.value = buildBookPages(panel.prefs, [...panel.sortRules])
  currentSpread.value = 0
  nextTick(attachSlotListeners)
}

function onSettingsChange({ prefs, sortRules }) {
  settings.saveSetting('bookPrefs', prefs)
  settings.saveSetting('bookSortRules', sortRules)
  rebuildBook()
}

function prevSpread() { if (currentSpread.value > 0) { currentSpread.value--; nextTick(attachSlotListeners) } }
function nextSpread() { if (currentSpread.value < totalSpreads.value - 1) { currentSpread.value++; nextTick(attachSlotListeners) } }

function attachSlotListeners() {
  document.querySelectorAll('.book-slot[data-id]').forEach(el => {
    el.addEventListener('click', () => {
      const id = Number(el.dataset.id)
      const card = store.allCards.find(c => c.id === id)
      if (card) { modalCard.value = card; modalCardId.value = id; cardModalVisible.value = true }
    })
  })
}

function onCardModalClose() { cardModalVisible.value = false; loadData() }
function onCardDeleted() { cardModalVisible.value = false; loadData() }
function onSplit(card) { splitCard.value = card; splitModalVisible.value = true }
function onSplitDone() { splitModalVisible.value = false; cardModalVisible.value = false; loadData() }

async function loadData() {
  if (store.allCards.length === 0) {
    await store.loadCollection()
  }
  rebuildBook()
}

onMounted(loadData)
</script>
