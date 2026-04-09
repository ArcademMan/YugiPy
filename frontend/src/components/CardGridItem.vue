<template>
  <div class="card-item" @click="$emit('click', card.id)">
    <div class="card-img-wrapper">
      <img :src="cardImgUrl(card.image_url)" :alt="card.name" loading="lazy">
      <span v-if="card.quantity > 1" class="card-overlay-qty">x{{ card.quantity }}</span>
      <span
        v-if="displayPrice.price && !card.price_manual"
        class="price-auto-dot"
        :class="dotClass"
        :title="dotTitle"
      ></span>
    </div>
    <div class="card-info">
      <div class="card-name" :title="card.name">{{ card.name }}</div>
      <div v-if="card.set_code" class="card-meta">{{ card.set_code }}</div>
      <div class="card-meta">{{ card.rarity }}</div>
      <div class="card-bottom-row">
        <span v-if="condTag" class="cond-tag" :style="{ background: condTag[1] }">{{ condTag[0] }}</span>
        <span class="card-bottom-lang"><LangFlag :lang="card.lang" /></span>
        <span v-if="displayPrice.price" class="card-price">{{ Number(displayPrice.price).toFixed(2) }}&euro;</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { cardImgUrl } from '../utils/images.js'
import { getDisplayPrice } from '../utils/price.js'
import { useSettingsStore } from '../stores/settings.js'
import LangFlag from './LangFlag.vue'

const props = defineProps({
  card: { type: Object, required: true }
})

defineEmits(['click'])

const settings = useSettingsStore()

const COND_TAG = {
  "Mint": ["MT", "#00bcd4"],
  "Near Mint": ["NM", "#4caf50"],
  "Excellent": ["EX", "#8bc34a"],
  "Good": ["GD", "#fdd835"],
  "Light Played": ["LP", "#ff9800"],
  "Played": ["PL", "#ff5722"],
  "Poor": ["PO", "#f44336"]
}

const displayPrice = computed(() => getDisplayPrice(props.card, settings.priceDisplayMode))
const condTag = computed(() => COND_TAG[props.card.condition] || null)
const dotClass = computed(() => {
  const dot = displayPrice.value.dot
  return dot === 'cm' ? 'price-dot-cm' : dot === 'fallback' ? 'price-dot-fallback' : ''
})
const dotTitle = computed(() => {
  const dot = displayPrice.value.dot
  return dot === 'cm' ? 'Cardmarket price' : dot === 'fallback' ? 'Fallback price (selected source unavailable)' : 'Automatic price'
})
</script>
