<template>
  <section>
    <div class="page-header">
      <h1>Results</h1>
      <p class="ocr-extracted-text">{{ scannerStore.extractedText }}</p>
    </div>

    <div class="card-grid">
      <p v-if="scannerStore.scanResults.length === 0">No results found. Try again with a better photo.</p>
      <div v-for="card in scannerStore.scanResults" :key="card.card_id" class="card-item scan-result-card">
        <img :src="cardImgUrl(card.image_url)" :alt="card.name" loading="lazy">
        <div class="card-info">
          <div class="card-name" :title="card.name">{{ card.name }}</div>
          <div class="card-meta">{{ card.type }}</div>
          <button class="btn-add" @click.stop="onAdd(card)">Add</button>
          <details v-if="card.sets && card.sets.length > 0" class="sets-details">
            <summary>{{ card.sets.length }} expansions</summary>
            <div class="card-sets-list">
              <div v-for="s in card.sets" :key="s.set_code" class="card-set-item">
                <span class="set-code">{{ s.set_code }}</span>
                <span class="set-name">{{ s.set_name }}</span>
                <span class="set-rarity">{{ s.set_rarity }}</span>
                <span v-if="s.set_price" class="set-price">{{ s.set_price }}&euro;</span>
              </div>
            </div>
          </details>
        </div>
      </div>
    </div>

    <button class="btn-secondary btn-full" @click="backToScanner">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>
      Scan another
    </button>

    <AddCardModal
      :visible="addModalVisible"
      :cardData="addCardData"
      :sets="addCardSets"
      @close="addModalVisible = false"
      @added="onCardAdded"
    />
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useScannerStore } from '../stores/scanner.js'
import { cardImgUrl } from '../utils/images.js'
import AddCardModal from '../components/AddCardModal.vue'

const router = useRouter()
const scannerStore = useScannerStore()

const addModalVisible = ref(false)
const addCardData = ref(null)
const addCardSets = ref([])

function onAdd(card) {
  const cardForAdd = { ...card }
  const sets = card.sets || []
  delete cardForAdd.sets
  addCardData.value = cardForAdd
  addCardSets.value = sets
  addModalVisible.value = true
}

function onCardAdded() {
  addModalVisible.value = false
}

function backToScanner() {
  scannerStore.clear()
  router.push('/scanner')
}
</script>
