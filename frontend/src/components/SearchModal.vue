<template>
  <div class="modal" :hidden="!visible">
    <div class="modal-backdrop" @click="$emit('close')"></div>
    <div class="modal-content modal-large">
      <button class="modal-close" @click="$emit('close')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <h2>Add card</h2>
      <div class="search-bar" style="margin-bottom:16px">
        <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <input
          ref="searchInput"
          type="text"
          v-model="query"
          placeholder="Name or set code (e.g. Ash Blossom, BLMR-IT065, BLMR...)"
          @input="onInput"
        >
      </div>
      <div class="card-grid">
        <p v-if="!results" class="text-muted">Search for a card by name to add it to the collection.</p>
        <p v-else-if="results.length === 0">No results for this search.</p>
        <template v-else>
          <div v-for="card in results" :key="card.card_id" class="card-item">
            <img :src="cardImgUrl(card.image_url)" :alt="card.name" loading="lazy">
            <div class="card-info">
              <div class="card-name" :title="card.name">{{ card.name }}</div>
              <div class="card-meta">{{ card.type }}</div>
              <button class="btn-add" @click.stop="onAdd(card)">Add</button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import api from '../api.js'
import { cardImgUrl } from '../utils/images.js'

const props = defineProps({
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'add'])

const query = ref('')
const results = ref(null)
const searchInput = ref(null)
let searchTimeout = null

watch(() => props.visible, async (val) => {
  if (val) {
    query.value = ''
    results.value = null
    await nextTick()
    searchInput.value?.focus()
  }
})

function onInput() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(doSearch, 400)
}

async function doSearch() {
  const q = query.value.trim()
  if (q.length < 2) {
    results.value = null
    return
  }
  try {
    results.value = await api.searchCards(q)
  } catch (e) {
    console.error(e)
  }
}

function onAdd(card) {
  const cardData = { ...card }
  const sets = card.sets || []
  delete cardData.sets
  emit('add', cardData, sets)
}
</script>
