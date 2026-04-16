<template>
  <div class="modal" :hidden="!visible">
    <div class="modal-backdrop" @click="$emit('close')"></div>
    <div class="modal-content">
      <button class="modal-close" @click="$emit('close')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <!-- Header: image + details (same as CardModal) -->
      <div class="modal-body" v-if="cardData">
        <div class="modal-img-wrapper">
          <button v-show="images.length > 1" class="modal-img-arrow modal-img-arrow-left" @click="switchImage(-1)">&lsaquo;</button>
          <img :src="currentImage" alt="">
          <button v-show="images.length > 1" class="modal-img-arrow modal-img-arrow-right" @click="switchImage(1)">&rsaquo;</button>
          <span v-show="images.length > 1" class="modal-img-counter">{{ currentIndex + 1 }} / {{ images.length }}</span>
        </div>
        <div id="modal-details">
          <p><strong>{{ cardData.name }}</strong></p>
          <p>{{ cardData.type }} {{ cardData.race ? '/ ' + cardData.race : '' }}</p>
          <p v-if="cardData.atk != null">ATK: {{ cardData.atk }} / DEF: {{ cardData.def_ ?? '?' }}</p>
          <p v-if="cardData.archetype">Archetype: {{ cardData.archetype }}</p>
        </div>
      </div>

      <!-- Collection fields (same layout as CardModal) -->
      <div id="modal-collection-info" v-if="cardData">
        <div class="form-group">
          <label>Expansion</label>
          <select v-model="selectedSet" @change="onSetChange">
            <option v-for="s in sortedSets" :key="s.set_code" :value="s" style="color:#ffb74d">
              {{ s.set_code }} &mdash; {{ s.set_name }} ({{ s.set_rarity }}){{ s.set_price ? ` \u2014 ${s.set_price}\u20AC` : '' }}
            </option>
            <option v-if="!sortedSets.length" :value="fallbackSet">No expansion found</option>
            <option :value="customSetMarker">Other...</option>
          </select>
        </div>
        <div class="form-group" v-if="showCustomSetCode">
          <label>Custom Set Code</label>
          <input type="text" v-model="customSetCode" placeholder="e.g. BLMR-IT065">
        </div>
        <div class="form-row">
          <div class="form-group" style="flex:2">
            <label>Rarity</label>
            <select v-model="rarity">
              <option v-for="r in allRarityOptions" :key="r" :value="r">{{ r }}</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Condition</label>
            <select v-model="condition">
              <option v-for="c in CONDITION_OPTIONS" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>Language <LangFlag :lang="lang" /></label>
            <select v-model="lang">
              <option v-for="l in LANG_OPTIONS" :key="l.value" :value="l.value">{{ l.label }}</option>
            </select>
          </div>
        </div>
        <div class="form-group">
          <label>Location <span class="text-muted">(optional)</span></label>
          <input type="text" v-model="location" placeholder="e.g. binder, deck blue-eyes...">
        </div>
      </div>

      <!-- Actions (same style as CardModal) -->
      <div class="modal-actions" v-if="cardData">
        <div class="qty-control">
          <button class="btn-qty" @click="qty = Math.max(1, qty - 1)">-</button>
          <span>x{{ qty }}</span>
          <button class="btn-qty" @click="qty++">+</button>
        </div>
        <button class="btn-primary btn-sm" @click="confirm">Add to collection</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { RARITY_OPTIONS, CONDITION_OPTIONS, LANG_OPTIONS } from '../utils/constants.js'
import { cardImgUrl } from '../utils/images.js'
import { useSettingsStore } from '../stores/settings.js'
import { useToast } from '../composables/useToast.js'
import LangFlag from './LangFlag.vue'
import api from '../api.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  cardData: { type: Object, default: null },
  sets: { type: Array, default: () => [] }
})

const emit = defineEmits(['close', 'added'])
const settings = useSettingsStore()
const { showToast } = useToast()

// Remember last set code used across scans (session only)
let lastSetCode = ''

const fallbackSet = { set_code: 'N/A', set_rarity: 'Common', set_name: 'Unknown', set_price: null }
const customSetMarker = { set_code: '__other__', set_rarity: '', set_name: 'Other', set_price: null }
const sortedSets = computed(() => [...props.sets].sort((a, b) => (a.set_code || '').localeCompare(b.set_code || '')))
const selectedSet = ref(null)
const showCustomSetCode = ref(false)
const customSetCode = ref('')
const rarity = ref('Common')
const condition = ref(settings.lastCondition)
const lang = ref(settings.lastLang || settings.defaultLang)
const qty = ref(1)
const location = ref('')

// Image carousel
const images = ref([])
const currentIndex = ref(0)
const currentImage = ref('')

function switchImage(delta) {
  if (images.value.length <= 1) return
  currentIndex.value = (currentIndex.value + delta + images.value.length) % images.value.length
  currentImage.value = images.value[currentIndex.value].display
}

// All rarity options, including current rarity if not in the standard list
const allRarityOptions = computed(() => {
  const opts = [...RARITY_OPTIONS]
  if (rarity.value && !opts.includes(rarity.value)) opts.push(rarity.value)
  return opts
})

function onSetChange() {
  if (selectedSet.value === customSetMarker) {
    showCustomSetCode.value = true
    customSetCode.value = ''
  } else {
    showCustomSetCode.value = false
    syncRarity()
  }
}

function syncRarity() {
  if (selectedSet.value?.set_rarity) {
    rarity.value = selectedSet.value.set_rarity
  }
}

watch(() => props.visible, async (val) => {
  if (!val || !props.cardData) return
  // Try to auto-select last used set prefix (e.g. "BLMR" from "BLMR-IT065")
  const lastPrefix = lastSetCode ? lastSetCode.split('-')[0] : ''
  const lastMatch = lastPrefix ? sortedSets.value.find(s => s.set_code && s.set_code.split('-')[0] === lastPrefix) : null
  selectedSet.value = lastMatch || sortedSets.value[0] || fallbackSet
  syncRarity()
  showCustomSetCode.value = false
  customSetCode.value = ''
  lang.value = settings.lastLang || settings.defaultLang
  condition.value = settings.lastCondition
  qty.value = 1
  location.value = ''

  // Initialize image carousel
  images.value = [{ display: cardImgUrl(props.cardData.image_url), raw: props.cardData.image_url }]
  currentIndex.value = 0
  currentImage.value = cardImgUrl(props.cardData.image_url)

  // Fetch all image variants
  try {
    const resp = await fetch(`https://db.ygoprodeck.com/api/v7/cardinfo.php?name=${encodeURIComponent(props.cardData.name)}`)
    if (resp.ok) {
      const data = await resp.json()
      const cardImages = data.data?.[0]?.card_images || []
      if (cardImages.length > 1) {
        images.value = cardImages.map(i => ({ display: cardImgUrl(i.image_url), raw: i.image_url }))
        const idx = images.value.findIndex(i => i.raw === props.cardData.image_url)
        currentIndex.value = idx >= 0 ? idx : 0
        currentImage.value = images.value[currentIndex.value].display
      }
    }
  } catch { /* ignore */ }
})

async function confirm() {
  if (!props.cardData) return
  const set = selectedSet.value || fallbackSet
  const locationArr = location.value.trim() ? location.value.split(',').map(s => s.trim()).filter(Boolean) : null
  // Use custom set code if "Other..." was selected
  let setCode = null
  if (showCustomSetCode.value) {
    setCode = customSetCode.value.trim() || null
  } else if (set.set_code && set.set_code !== 'N/A') {
    setCode = set.set_code
  }
  // Use selected image from carousel
  const selectedImageUrl = images.value.length > 0 ? images.value[currentIndex.value].raw : props.cardData.image_url
  const payload = {
    ...props.cardData,
    image_url: selectedImageUrl,
    set_code: setCode,
    rarity: rarity.value,
    condition: condition.value,
    lang: lang.value,
    location: locationArr,
    quantity: qty.value
  }
  if (!showCustomSetCode.value && set.set_price && set.set_price > 0) {
    payload.price_cardmarket = set.set_price
  }
  try {
    await api.addCard(payload)
    settings.setLastLang(lang.value)
    settings.setLastCondition(condition.value)
    lastSetCode = setCode || ''
    showToast('Card added to collection!')
    emit('added')
    emit('close')
  } catch (e) {
    console.error(e)
    alert('Error adding card')
  }
}
</script>
