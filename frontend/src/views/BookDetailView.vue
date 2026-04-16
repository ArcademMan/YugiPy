<template>
  <section v-if="book">
    <div class="page-header">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <router-link to="/books" class="btn-secondary btn-sm">&larr;</router-link>
        <h1>{{ book.name }}</h1>
        <span class="stats-badge">{{ statsText }}</span>
        <span class="stats-badge stats-badge-warn" v-if="wastedSlots > 0" title="Empty slots from group separation">{{ wastedSlots }} wasted</span>
        <span
          class="stats-badge stats-badge-danger"
          v-if="overflowCards.length > 0"
          style="cursor:pointer"
          title="Cards that don't fit — click to see"
          @click="overflowVisible = true"
        >{{ overflowCards.length }} excluded</span>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn-secondary" @click="settingsVisible = true" title="Settings">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
        </button>
        <button class="btn-secondary" @click="openAddCards">+ Add cards</button>
        <button class="btn-secondary" @click="doAutoAssign" :disabled="autoAssigning">
          {{ autoAssigning ? 'Assigning...' : 'Auto-fill' }}
        </button>
        <button class="btn-danger btn-sm" @click="confirmReset = true" :disabled="booksStore.bookCards.length === 0">
          Reset
        </button>
      </div>
    </div>

    <BookSettingsPanel
      :visible="settingsVisible"
      :availableSets="availableSets"
      :availableArchetypes="availableArchetypes"
      :archetypeAvailability="archetypeAvailability"
      :initialPrefs="bookPrefs"
      :initialSortRules="bookSortRules"
      ref="settingsPanel"
      @change="onSettingsChange"
      @close="settingsVisible = false"
    />

    <div class="book-main">
      <div class="book-spread">
          <div class="book-page" v-for="pageIdx in spreadPages" :key="pageIdx">
            <div class="book-page-header" v-if="pages[pageIdx] && pages[pageIdx].group">
              {{ pages[pageIdx].group }}
            </div>
            <div class="book-page-grid" :style="gridStyle">
              <template v-if="pages[pageIdx]">
                <div
                  v-for="(card, slotIdx) in pages[pageIdx].slots"
                  :key="slotIdx"
                  class="book-slot"
                  :class="{
                    empty: !card,
                    pinned: isPinned(pageIdx, slotIdx),
                    'drag-over': dragOverKey === `${pageIdx}-${slotIdx}`
                  }"
                  :draggable="!!card"
                  @dragstart="onDragStart($event, pageIdx, slotIdx, card)"
                  @dragend="onDragEnd"
                  @dragover.prevent="onDragOver(pageIdx, slotIdx)"
                  @dragleave="onDragLeave"
                  @drop.prevent="onDrop(pageIdx, slotIdx)"
                  @click="onSlotClick(pageIdx, slotIdx, card)"
                  @contextmenu.prevent="onSlotContext(pageIdx, slotIdx, card)"
                >
                  <template v-if="card">
                    <img
                      :src="cardImgUrl(card.image_url)"
                      :alt="card.name"
                      :title="`${card.name}\n${card.set_code || ''} · ${card.rarity} · ${card.lang}`"
                      loading="lazy"
                    >
                    <span v-if="showPrices" class="book-slot-price">
                      {{ formatPrice(card) }}
                    </span>
                    <span v-if="isPinned(pageIdx, slotIdx)" class="book-slot-pin" title="Pinned">📌</span>
                  </template>
                  <span v-if="!card && dragSource" class="book-slot-drop-hint">Drop here</span>
                </div>
              </template>
            </div>
          </div>
        </div>
        <div class="book-nav">
          <button class="btn-secondary" :disabled="currentSpread <= 0" @click="prevSpread">&larr;</button>
          <span>{{ pageNumText }}</span>
          <button class="btn-secondary" :disabled="currentSpread >= totalSpreads - 1" @click="nextSpread">&rarr;</button>
      </div>
    </div>

    <!-- Slot context menu -->
    <div class="modal" :hidden="!contextMenu.visible">
      <div class="modal-backdrop" @click="contextMenu.visible = false"></div>
      <div class="modal-content" style="max-width:360px">
        <h2>{{ contextMenu.card?.name }}</h2>
        <p class="text-secondary" style="margin-bottom:16px">
          Page {{ contextMenu.page + 1 }}, slot {{ contextMenu.slot + 1 }}
          <template v-if="contextMenu.pinned"> · Pinned</template>
        </p>
        <div style="display:flex;flex-direction:column;gap:8px">
          <button class="btn-secondary" @click="contextViewCard">View card details</button>
          <button class="btn-secondary" v-if="contextMenu.pinned" @click="contextUnpin">Unpin from slot</button>
          <button class="btn-secondary" v-if="!contextMenu.pinned" @click="contextPin">Pin to this slot</button>
          <button class="btn-danger" @click="contextRemove">Remove from book</button>
        </div>
      </div>
    </div>

    <!-- Card picker (for empty slot pin OR add cards) -->
    <div class="modal" :hidden="!pickerVisible">
      <div class="modal-backdrop" @click="pickerVisible = false"></div>
      <div class="modal-content modal-large">
        <h2>{{ pickerMode === 'pin' ? `Pick card for page ${pinTarget.page + 1}, slot ${pinTarget.slot + 1}` : 'Add cards to book' }}</h2>
        <input
          v-model="pickerSearch"
          type="text"
          placeholder="Search cards..."
          class="picker-search"
          ref="pickerSearchInput"
        >
        <div class="picker-grid">
          <div
            v-for="card in filteredPickerCards"
            :key="card.id"
            class="picker-card"
            @click="onPickerSelect(card)"
          >
            <img :src="cardImgUrl(card.image_url)" :alt="card.name" loading="lazy">
            <span class="picker-card-name">{{ card.name }}</span>
          </div>
        </div>
        <p v-if="filteredPickerCards.length === 0" class="text-secondary" style="text-align:center;padding:24px 0">
          No cards found
        </p>
        <div class="modal-actions">
          <button class="btn-secondary" @click="pickerVisible = false">Close</button>
        </div>
      </div>
    </div>

    <!-- Reset confirm -->
    <div class="modal" :hidden="!confirmReset">
      <div class="modal-backdrop" @click="confirmReset = false"></div>
      <div class="modal-content" style="max-width:400px">
        <h2>Reset book?</h2>
        <p>This will remove all card assignments and pins from "{{ book.name }}".</p>
        <div class="modal-actions">
          <button class="btn-secondary" @click="confirmReset = false">Cancel</button>
          <button class="btn-danger" @click="doReset">Reset</button>
        </div>
      </div>
    </div>

    <!-- Card detail modal -->
    <CardModal
      :visible="cardModalVisible"
      :card="modalCard"
      :cardId="modalCardId"
      @close="cardModalVisible = false"
      @updated="reload"
      @deleted="onCardDeleted"
      @split="onSplit"
    />
    <SplitModal
      :visible="splitModalVisible"
      :card="splitCard"
      @close="splitModalVisible = false"
      @split="onSplitDone"
    />

    <!-- Overflow cards modal -->
    <div class="modal" :hidden="!overflowVisible">
      <div class="modal-backdrop" @click="overflowVisible = false"></div>
      <div class="modal-content modal-large">
        <button class="modal-close" @click="overflowVisible = false">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
        <h2>Excluded cards ({{ overflowCards.length }})</h2>
        <p class="text-secondary" style="margin-bottom:12px">These cards don't fit in the available {{ book.page_count }} pages. Add more pages to include them.</p>
        <div class="overflow-list">
          <div v-for="(card, idx) in overflowCards" :key="idx" class="overflow-item">
            <img :src="cardImgUrl(card.image_url)" :alt="card.name" loading="lazy" class="overflow-thumb">
            <div class="overflow-info">
              <span class="overflow-name">{{ card.name }}</span>
              <span class="text-secondary">{{ card.set_code }} · {{ card.rarity }} · {{ card.archetype || 'No archetype' }}</span>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="overflowVisible = false">Close</button>
        </div>
      </div>
    </div>
  </section>
  <section v-else>
    <p>Loading...</p>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useCollectionStore } from '../stores/collection.js'
import { useSettingsStore } from '../stores/settings.js'
import { useBooksStore } from '../stores/books.js'
import { RARITY_ORDER, TYPE_GROUP, TYPE_ORDER } from '../utils/constants.js'
import { cardImgUrl } from '../utils/images.js'
import { getDisplayPrice } from '../utils/price.js'
import BookSettingsPanel from '../components/BookSettingsPanel.vue'
import CardModal from '../components/CardModal.vue'
import SplitModal from '../components/SplitModal.vue'
import api from '../api.js'

const route = useRoute()
const collectionStore = useCollectionStore()
const settings = useSettingsStore()
const booksStore = useBooksStore()

const settingsPanel = ref(null)
const currentSpread = ref(0)
const pages = ref([])
const autoAssigning = ref(false)
const confirmReset = ref(false)
const settingsVisible = ref(false)
const archetypeAvailability = ref({})
const overflowCards = ref([])
const overflowVisible = ref(false)

// Card modal
const cardModalVisible = ref(false)
const modalCard = ref(null)
const modalCardId = ref(null)
const splitModalVisible = ref(false)
const splitCard = ref(null)

// Card picker
const pickerVisible = ref(false)
const pickerSearch = ref('')
const pickerSearchInput = ref(null)
const pickerMode = ref('pin')  // 'pin' or 'add'
const pinTarget = ref({ page: 0, slot: 0 })

// Context menu for filled slot
const contextMenu = ref({ visible: false, page: 0, slot: 0, card: null, pinned: false })

// Drag & drop
const dragSource = ref(null)
const dragOverKey = ref(null)

const bookId = computed(() => Number(route.params.id))
const book = computed(() => booksStore.currentBook)

const showPrices = computed(() => settingsPanel.value?.prefs?.showPrices || false)

const bookPrefs = computed(() => {
  if (!book.value) return null
  return {
    groupBy: book.value.group_by,
    gridSize: book.value.grid_size,
    maxCopies: String(book.value.max_copies),
    copiesMode: book.value.copies_mode,
    filterLangs: book.value.filter_langs || [],
    filterConditions: book.value.filter_conditions || [],
    filterArchetypes: book.value.filter_archetypes || [],
    filterSets: book.value.filter_sets || [],
    minPrice: book.value.min_price,
    newPage: book.value.new_page,
    showPrices: book.value.show_prices,
    groupDuplicates: book.value.group_duplicates,
  }
})

const bookSortRules = computed(() => book.value?.sort_rules || ['rarity_desc'])

const availableSets = computed(() =>
  [...new Set(assignedCards.value.map(c => c.set_code ? c.set_code.split('-')[0] : '').filter(Boolean))].sort()
)

const availableArchetypes = computed(() =>
  [...new Set(collectionStore.allCards.map(c => c.archetype).filter(Boolean))].sort()
)

// Cards assigned to this book (full card objects from collection)
const assignedCards = computed(() => {
  const cardMap = new Map()
  for (const bc of booksStore.bookCards) {
    const card = collectionStore.allCards.find(c => c.id === bc.card_id)
    if (card) cardMap.set(card.id, { ...card, _assignedQty: bc.quantity })
  }
  return [...cardMap.values()]
})

// Set of card IDs assigned to this book
const assignedCardIds = computed(() => new Set(booksStore.bookCards.map(bc => bc.card_id)))

// Pinned cards lookup: card_id -> BookSlot record
const pinMap = computed(() => {
  const m = new Map()
  for (const s of booksStore.bookSlots) {
    m.set(s.card_id, s)
  }
  return m
})

// Set of "page-slot" keys that are pinned (built during buildPages)
const pinnedSlotKeys = ref(new Set())

function isPinned(page, slot) {
  return pinnedSlotKeys.value.has(`${page}-${slot}`)
}

const gridStyle = computed(() => {
  const gs = settingsPanel.value?.prefs?.gridSize || book.value?.grid_size || '3x3'
  const cols = parseInt(gs.split('x')[0])
  return { 'grid-template-columns': `repeat(${cols}, 1fr)` }
})

const filledSlots = computed(() =>
  pages.value.reduce((s, p) => s + p.slots.filter(Boolean).length, 0)
)
const totalSlots = computed(() =>
  pages.value.reduce((s, p) => s + p.slots.length, 0)
)
const wastedSlots = computed(() => totalSlots.value - filledSlots.value)

const statsText = computed(() =>
  `${filledSlots.value} cards · ${totalSlots.value} slots · ${pages.value.length} pages`
)

// Book-like spreads: first page is single (cover), then pairs offset by 1
// Spread 0: [page 0]   (cover)
// Spread 1: [page 1, page 2]   (back of sheet 1 + front of sheet 2)
// Spread 2: [page 3, page 4]
// ...
const totalSpreads = computed(() => {
  const n = pages.value.length
  if (n <= 0) return 0
  return Math.ceil((n + 1) / 2)
})

const pageNumText = computed(() => {
  const n = pages.value.length
  if (n <= 0) return 'No cards'
  const sp = spreadPages.value
  const labels = sp.map(i => i + 1).join('-')
  return `${labels} / ${n}`
})

const spreadPages = computed(() => {
  const n = pages.value.length
  if (n <= 0) return []
  if (currentSpread.value === 0) return [0]
  const left = currentSpread.value * 2 - 1
  const right = left + 1
  const result = []
  if (left < n) result.push(left)
  if (right < n) result.push(right)
  return result
})

// Cards for the picker — depends on mode
const filteredPickerCards = computed(() => {
  let cards
  if (pickerMode.value === 'pin') {
    // Pin mode: show assigned cards that aren't already pinned
    const pinnedCardIds = new Set(booksStore.bookSlots.map(s => s.card_id))
    cards = assignedCards.value.filter(c => !pinnedCardIds.has(c.id))
  } else {
    // Add mode: show all collection cards not yet assigned to this book
    cards = collectionStore.allCards.filter(c => !assignedCardIds.value.has(c.id))
  }
  if (pickerSearch.value) {
    const q = pickerSearch.value.toLowerCase()
    cards = cards.filter(c =>
      c.name.toLowerCase().includes(q) ||
      (c.archetype || '').toLowerCase().includes(q) ||
      (c.set_code || '').toLowerCase().includes(q)
    )
  }
  return cards.slice(0, 60)
})

function formatPrice(card) {
  const { price } = getDisplayPrice(card, settings.priceDisplayMode)
  return price ? `${Number(price).toFixed(2)}€` : ''
}

// ── Page builder ─────────────────────────────────────────────────────

function buildPages(prefs, sortRulesArr) {
  if (!book.value) return []

  const groupBy = prefs.groupBy || 'archetype'
  const newPagePerGroup = prefs.newPage !== false
  const groupDuplicates = prefs.groupDuplicates || false
  const gridSize = prefs.gridSize || '3x3'
  const [cols, rows] = gridSize.split('x').map(Number)
  const slotsPerPage = cols * rows
  const maxPages = book.value.page_count
  const maxCopies = parseInt(prefs.maxCopies) || 0
  const copiesMode = prefs.copiesMode || 'entry'

  let cards = [...assignedCards.value]

  // Expand by assigned quantity
  const expanded = []
  if (maxCopies > 0 && copiesMode === 'name') {
    const nameCount = new Map()
    for (const card of cards) {
      const used = nameCount.get(card.name) || 0
      const remaining = maxCopies - used
      if (remaining <= 0) continue
      const copies = Math.min(card._assignedQty, remaining)
      nameCount.set(card.name, used + copies)
      for (let i = 0; i < copies; i++) expanded.push(card)
    }
  } else {
    for (const card of cards) {
      const copies = maxCopies > 0 ? Math.min(card._assignedQty, maxCopies) : card._assignedQty
      for (let i = 0; i < copies; i++) expanded.push(card)
    }
  }

  // Group ALL expanded cards (before removing pins)
  function getGroupKey(card) {
    switch (groupBy) {
      case 'set': return card.set_code ? card.set_code.split('-')[0] : 'Other'
      case 'archetype': return card.archetype || 'No archetype'
      case 'type': return TYPE_GROUP[card.type] || card.type || 'Other'
      default: return ''
    }
  }

  const groups = new Map()
  for (const card of expanded) {
    const key = getGroupKey(card)
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
    archetype_desc: (a, b) => (b.archetype || '').localeCompare(a.archetype || ''),
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

  // When groupDuplicates is on, cluster same-name cards together
  function clusterByName(cards) {
    if (!groupDuplicates) return cards
    const nameGroups = new Map()
    for (const card of cards) {
      if (!nameGroups.has(card.name)) nameGroups.set(card.name, [])
      nameGroups.get(card.name).push(card)
    }
    const seen = new Set()
    const out = []
    for (const card of cards) {
      if (seen.has(card.name)) continue
      seen.add(card.name)
      out.push(...nameGroups.get(card.name))
    }
    return out
  }

  // Build pin lookup: group_key -> [{position, card_id}]
  const pinsByGroup = new Map()
  for (const pin of booksStore.bookSlots) {
    const key = pin.group_key
    if (!pinsByGroup.has(key)) pinsByGroup.set(key, [])
    pinsByGroup.get(key).push(pin)
  }

  // For each group, build the ordered card list respecting pins
  function buildGroupCards(key) {
    let sorted = clusterByName((groups.get(key) || []).sort(sortFn))
    const pins = pinsByGroup.get(key) || []
    if (pins.length === 0) return sorted

    // Remove pinned cards from the sorted list (1 copy per pin)
    const pinnedIds = new Map()
    for (const p of pins) pinnedIds.set(p.card_id, (pinnedIds.get(p.card_id) || 0) + 1)
    const removedCounts = new Map()
    sorted = sorted.filter(c => {
      const pinCount = pinnedIds.get(c.id) || 0
      const removed = removedCounts.get(c.id) || 0
      if (removed < pinCount) {
        removedCounts.set(c.id, removed + 1)
        return false
      }
      return true
    })

    // Insert pinned cards at their positions, marking them
    const final = [...sorted]
    for (const pin of pins.sort((a, b) => a.position - b.position)) {
      const card = collectionStore.allCards.find(c => c.id === pin.card_id)
      if (!card) continue
      const pos = Math.min(pin.position, final.length)
      final.splice(pos, 0, { ...card, _pinned: true })
    }
    return final
  }

  // Also handle groups that only exist via pins (no auto-flow cards)
  for (const key of pinsByGroup.keys()) {
    if (!groups.has(key)) groups.set(key, [])
    if (!sortedKeys.includes(key)) sortedKeys.push(key)
  }

  const result = []
  if (groupBy === 'none' || !newPagePerGroup) {
    const allCards = []
    for (const key of sortedKeys) allCards.push(...buildGroupCards(key))
    for (let i = 0; i < allCards.length; i += slotsPerPage) {
      result.push({ group: null, slots: allCards.slice(i, i + slotsPerPage) })
    }
  } else {
    for (const key of sortedKeys) {
      const groupCards = buildGroupCards(key)
      if (groupCards.length === 0) continue
      for (let i = 0; i < groupCards.length; i += slotsPerPage) {
        result.push({ group: key, slots: groupCards.slice(i, i + slotsPerPage) })
      }
      // Pad last page of the group
      const lastPage = result[result.length - 1]
      while (lastPage.slots.length < slotsPerPage) lastPage.slots.push(null)
      // Pad to complete the sheet (front+back = 2 pages per sheet)
      if (result.length % 2 !== 0) {
        result.push({ group: key, slots: Array(slotsPerPage).fill(null) })
      }
    }
  }

  // Pad last page
  if (result.length > 0) {
    const lastPage = result[result.length - 1]
    while (lastPage.slots.length < slotsPerPage) lastPage.slots.push(null)
  }

  const keptPages = result.slice(0, maxPages)
  const droppedPages = result.slice(maxPages)

  // Collect cards that didn't fit
  const overflow = []
  for (const p of droppedPages) {
    for (const card of p.slots) {
      if (card) overflow.push(card)
    }
  }

  return { pages: keptPages, overflow }
}

function rebuildBook() {
  const panel = settingsPanel.value
  if (!panel || !book.value) return
  const built = buildPages(panel.prefs, [...panel.sortRules])
  pages.value = built.pages
  overflowCards.value = built.overflow
  // Build pinned slot keys from _pinned markers
  const keys = new Set()
  for (let p = 0; p < built.pages.length; p++) {
    for (let s = 0; s < built.pages[p].slots.length; s++) {
      if (built.pages[p].slots[s]?._pinned) keys.add(`${p}-${s}`)
    }
  }
  pinnedSlotKeys.value = keys
  currentSpread.value = Math.min(currentSpread.value, Math.max(0, totalSpreads.value - 1))
}

async function onSettingsChange({ prefs, sortRules }) {
  await booksStore.updateBook(bookId.value, {
    group_by: prefs.groupBy,
    grid_size: prefs.gridSize,
    max_copies: parseInt(prefs.maxCopies) || 0,
    copies_mode: prefs.copiesMode,
    filter_langs: prefs.filterLangs,
    filter_conditions: prefs.filterConditions,
    filter_archetypes: prefs.filterArchetypes,
    filter_sets: prefs.filterSets,
    min_price: prefs.minPrice || 0,
    new_page: prefs.newPage,
    show_prices: prefs.showPrices,
    group_duplicates: prefs.groupDuplicates,
    sort_rules: sortRules,
  })
  rebuildBook()
}

function prevSpread() { if (currentSpread.value > 0) currentSpread.value-- }
function nextSpread() { if (currentSpread.value < totalSpreads.value - 1) currentSpread.value++ }

// ── Drag & drop ──────────────────────────────────────────────────────

function onDragStart(e, pageIdx, slotIdx, card) {
  if (!card) return
  dragSource.value = { page: pageIdx, slot: slotIdx, card }
  e.dataTransfer.effectAllowed = 'move'
  if (e.target.querySelector('img')) {
    e.dataTransfer.setDragImage(e.target.querySelector('img'), 30, 40)
  }
}

function onDragEnd() {
  dragSource.value = null
  dragOverKey.value = null
}

function onDragOver(pageIdx, slotIdx) {
  if (!dragSource.value) return
  dragOverKey.value = `${pageIdx}-${slotIdx}`
}

function onDragLeave() {
  dragOverKey.value = null
}

async function onDrop(toPage, toSlot) {
  dragOverKey.value = null
  const src = dragSource.value
  if (!src) return
  dragSource.value = null

  if (src.page === toPage && src.slot === toSlot) return

  const srcCard = src.card
  const targetCard = pages.value[toPage]?.slots[toSlot] || null

  // Swap cards directly in the UI first (no rebuild, avoids page shifting)
  pages.value[toPage].slots[toSlot] = srcCard
  pages.value[src.page].slots[src.slot] = targetCard

  try {
    // Calculate group-relative positions and persist pins
    const srcPin = slotToGroupPosition(toPage, toSlot)
    await booksStore.pinSlot(bookId.value, srcPin.groupKey, srcPin.position, srcCard.id)
    if (targetCard) {
      const tgtPin = slotToGroupPosition(src.page, src.slot)
      await booksStore.pinSlot(bookId.value, tgtPin.groupKey, tgtPin.position, targetCard.id)
    }
    await booksStore.loadBookSlots(bookId.value)
  } catch (e) {
    console.warn('Drag-drop failed:', e)
    rebuildBook()
  }
}

// Convert a visual page+slot to a group-relative {groupKey, position}
function slotToGroupPosition(pageIdx, slotIdx) {
  const page = pages.value[pageIdx]
  const groupKey = page?.group || ''
  // Count all filled slots in this group's pages before this slot
  let position = 0
  for (let p = 0; p < pages.value.length; p++) {
    if (pages.value[p].group !== page?.group) continue
    const slots = pages.value[p].slots
    for (let s = 0; s < slots.length; s++) {
      if (p === pageIdx && s === slotIdx) return { groupKey, position }
      if (slots[s]) position++
    }
  }
  return { groupKey, position }
}

// ── Slot click & context menu ────────────────────────────────────────

function onSlotClick(pageIdx, slotIdx, card) {
  if (card) {
    // Open context menu for filled slot
    onSlotContext(pageIdx, slotIdx, card)
  } else {
    // Empty slot: open picker to pin a card from collection
    pickerMode.value = 'pin'
    pinTarget.value = { page: pageIdx, slot: slotIdx }
    pickerSearch.value = ''
    pickerVisible.value = true
    nextTick(() => pickerSearchInput.value?.focus())
  }
}

function onSlotContext(pageIdx, slotIdx, card) {
  if (!card) return
  contextMenu.value = {
    visible: true,
    page: pageIdx,
    slot: slotIdx,
    card,
    pinned: isPinned(pageIdx, slotIdx),
  }
}

function contextViewCard() {
  const card = contextMenu.value.card
  contextMenu.value.visible = false
  modalCard.value = card
  modalCardId.value = card.id
  cardModalVisible.value = true
}

async function contextUnpin() {
  const card = contextMenu.value.card
  const pin = pinMap.value.get(card?.id)
  contextMenu.value.visible = false
  if (pin) {
    await booksStore.unpinSlot(bookId.value, pin.id)
    rebuildBook()
  }
}

async function contextPin() {
  const { page, slot, card } = contextMenu.value
  contextMenu.value.visible = false
  try {
    const gp = slotToGroupPosition(page, slot)
    await booksStore.pinSlot(bookId.value, gp.groupKey, gp.position, card.id)
    rebuildBook()
  } catch (e) {
    console.warn('Pin failed:', e)
  }
}

async function contextRemove() {
  const card = contextMenu.value.card
  contextMenu.value.visible = false
  try {
    await booksStore.unassignCard(bookId.value, card.id)
    await booksStore.loadBook(bookId.value)
    rebuildBook()
  } catch (e) {
    console.warn('Remove failed:', e)
  }
}

// ── Card picker ──────────────────────────────────────────────────────

function openAddCards() {
  pickerMode.value = 'add'
  pickerSearch.value = ''
  pickerVisible.value = true
  nextTick(() => pickerSearchInput.value?.focus())
}

async function onPickerSelect(card) {
  try {
    if (pickerMode.value === 'pin') {
      // Assign if not yet assigned, then pin
      if (!assignedCardIds.value.has(card.id)) {
        await booksStore.assignCard(bookId.value, card.id, card.quantity)
      }
      const gp = slotToGroupPosition(pinTarget.value.page, pinTarget.value.slot)
      await booksStore.pinSlot(bookId.value, gp.groupKey, gp.position, card.id)
      pickerVisible.value = false
      rebuildBook()
    } else {
      // Add mode: assign card to book (stays in picker for multi-add)
      await booksStore.assignCard(bookId.value, card.id, card.quantity)
      await booksStore.loadBook(bookId.value)
      rebuildBook()
    }
  } catch (e) {
    console.warn('Picker action failed:', e)
  }
}

// ── Bulk operations ──────────────────────────────────────────────────

async function doAutoAssign() {
  autoAssigning.value = true
  try {
    await booksStore.autoAssign(bookId.value)
    await reload()
  } finally {
    autoAssigning.value = false
  }
}

async function doReset() {
  confirmReset.value = false
  try {
    await api.resetBook(bookId.value)
    await reload()
  } catch (e) {
    console.warn('Reset failed:', e)
  }
}

// ── Card modal ───────────────────────────────────────────────────────

function onCardDeleted() { cardModalVisible.value = false; reload() }
function onSplit(card) { splitCard.value = card; splitModalVisible.value = true }
function onSplitDone() { splitModalVisible.value = false; cardModalVisible.value = false; reload() }

async function loadArchetypeAvailability() {
  try {
    const data = await api.getArchetypeAvailability(bookId.value)
    const map = {}
    for (const item of data) map[item.archetype] = item.available
    archetypeAvailability.value = map
  } catch (e) {
    console.warn('Failed to load archetype availability:', e)
  }
}

async function reload() {
  if (collectionStore.allCards.length === 0) await collectionStore.loadCollection()
  await Promise.all([
    booksStore.loadBook(bookId.value),
    loadArchetypeAvailability(),
  ])
  rebuildBook()
}

watch(bookId, () => reload())

onMounted(async () => {
  if (collectionStore.allCards.length === 0) await collectionStore.loadCollection()
  await Promise.all([
    booksStore.loadBook(bookId.value),
    loadArchetypeAvailability(),
  ])
  nextTick(rebuildBook)
})
</script>
