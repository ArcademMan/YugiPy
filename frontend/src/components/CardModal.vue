<template>
  <div class="modal" :hidden="!visible">
    <div class="modal-backdrop" @click="close"></div>
    <div class="modal-content">
      <button class="modal-close" @click="close">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <div class="modal-body" v-if="card">
        <div class="modal-img-wrapper">
          <button v-show="images.length > 1" class="modal-img-arrow modal-img-arrow-left" @click="switchImage(-1)">&lsaquo;</button>
          <img :src="currentImage" alt="">
          <button v-show="images.length > 1" class="modal-img-arrow modal-img-arrow-right" @click="switchImage(1)">&rsaquo;</button>
          <span v-show="images.length > 1" class="modal-img-counter">{{ currentIndex + 1 }} / {{ images.length }}</span>
        </div>
        <div id="modal-details">
          <p><strong>{{ card.name }}</strong></p>
          <p>{{ card.type }} {{ card.race ? '/ ' + card.race : '' }}</p>
          <p v-if="card.atk != null">ATK: {{ card.atk }} / DEF: {{ card.def_ ?? '?' }}</p>
          <p v-if="card.archetype">Archetype: {{ card.archetype }}</p>
          <div class="price-section">
            <div class="price-input-row">
              <label>Trend &euro;</label>
              <input type="number" step="0.01" min="0" v-model="priceValue" @change="onPriceManualEdit" placeholder="0.00">
              <button type="button" class="btn-icon" title="Update prices from Cardmarket" @click="refreshCmPrice" :disabled="cmRefreshing">{{ cmRefreshing ? '...' : 'CM' }}</button>
            </div>
            <div class="price-cm-details">
              <span title="Minimum">Min: <strong>{{ cmMin }}</strong></span>
              <span title="Average top 5">Avg: <strong>{{ cmAvg }}</strong></span>
              <span title="Median top 5">Med: <strong>{{ cmMedian }}</strong></span>
            </div>
            <a :href="cmSearchUrl" target="_blank" rel="noopener" class="cardmarket-link">View on Cardmarket &nearr;</a>
          </div>
        </div>
      </div>

      <div id="modal-collection-info" v-if="card">
        <div class="form-row">
          <div class="form-group" style="flex:2">
            <label>Rarity</label>
            <select v-model="editRarity" @change="saveField('rarity', editRarity)">
              <option v-for="r in rarityOptions" :key="r" :value="r">{{ r }}</option>
            </select>
          </div>
          <div class="form-group" style="flex:1">
            <label>Set Code</label>
            <select v-if="!showSetInput" v-model="editSetCode" @change="onSetCodeSelect">
              <option v-for="s in setCodeOptions" :key="s.value" :value="s.value" :style="s.style">{{ s.label }}</option>
            </select>
            <input v-else type="text" v-model="editSetCodeManual" @change="saveField('set_code', editSetCodeManual.trim() || null)" placeholder="e.g. BLMR-IT065">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Condition</label>
            <select v-model="editCondition" @change="saveField('condition', editCondition)">
              <option v-for="c in CONDITION_OPTIONS" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>Language <LangFlag :lang="editLang" /></label>
            <select v-model="editLang" @change="saveField('lang', editLang)">
              <option v-for="l in LANG_OPTIONS" :key="l.value" :value="l.value">{{ l.label }}</option>
            </select>
          </div>
        </div>
        <div class="form-group">
          <label>Location</label>
          <input type="text" v-model="editLocation" @change="saveLocationField" placeholder="e.g. binder, deck blue-eyes...">
        </div>
      </div>

      <div class="modal-actions" v-if="card">
        <div class="qty-control">
          <button class="btn-qty" @click="changeQty(-1)">-</button>
          <span>x{{ quantity }}</span>
          <button class="btn-qty" @click="changeQty(1)">+</button>
        </div>
        <button class="btn-secondary btn-sm" @click="$emit('split', card)" v-show="quantity > 1">Split</button>
        <button class="btn-danger btn-sm" @click="deleteCard">Remove</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, toRef } from 'vue'
import { RARITY_OPTIONS, CONDITION_OPTIONS, LANG_OPTIONS } from '../utils/constants.js'
import { cardImgUrl } from '../utils/images.js'
import { buildCardmarketUrl } from '../utils/price.js'
import { useSettingsStore } from '../stores/settings.js'
import { useToast } from '../composables/useToast.js'
import LangFlag from './LangFlag.vue'
import api from '../api.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  card: { type: Object, default: null },
  cardId: { type: Number, default: null }
})

const emit = defineEmits(['close', 'updated', 'split', 'deleted'])
const settings = useSettingsStore()
const { showToast } = useToast()

// Image carousel
const images = ref([])
const currentIndex = ref(0)
const currentImage = ref('')

function switchImage(delta) {
  if (images.value.length <= 1) return
  currentIndex.value = (currentIndex.value + delta + images.value.length) % images.value.length
  currentImage.value = images.value[currentIndex.value].display
  // Save image_url change
  api.updateCard(props.cardId, { image_url: images.value[currentIndex.value].raw })
}

// Editable fields
const editRarity = ref('')
const editCondition = ref('')
const editLang = ref('')
const editLocation = ref('')
const editSetCode = ref('')
const editSetCodeManual = ref('')
const showSetInput = ref(false)
const setCodeOptions = ref([])
const quantity = ref(1)

// Price
const priceValue = ref('')
const cmMin = ref('\u2014')
const cmAvg = ref('\u2014')
const cmMedian = ref('\u2014')
const cmRefreshing = ref(false)

const rarityOptions = computed(() => {
  const opts = [...RARITY_OPTIONS]
  if (editRarity.value && !opts.includes(editRarity.value)) opts.push(editRarity.value)
  return opts
})

const cmSearchUrl = computed(() => {
  if (!props.card) return '#'
  return buildCardmarketUrl(
    props.card.name, null, editRarity.value, editLang.value, editSetCode.value,
    settings.cmExpansions, settings.cmRarities
  )
})

// Pending saves tracking
const pendingSaves = []

async function saveField(field, value) {
  const p = api.updateCard(props.cardId, { [field]: value }).catch(e => {
    console.error(e)
    alert('Error saving')
  })
  pendingSaves.push(p)
  return p
}

function saveLocationField() {
  const loc = editLocation.value.trim() ? editLocation.value.split(',').map(s => s.trim()).filter(Boolean) : null
  saveField('location', loc)
}

function onSetCodeSelect() {
  if (editSetCode.value === '__other__') {
    showSetInput.value = true
    editSetCodeManual.value = ''
  } else {
    saveField('set_code', editSetCode.value || null)
  }
}

async function onPriceManualEdit() {
  const val = priceValue.value === '' ? null : parseFloat(priceValue.value)
  await api.updateCard(props.cardId, { price_cardmarket: val, price_manual: true })
}

async function refreshCmPrice() {
  cmRefreshing.value = true
  try {
    const result = await api.getCardCmPrice(props.cardId)
    if (result.error === 'extension_not_connected') {
      showToast('Firefox extension not connected')
    } else if (result.error) {
      showToast(`Error: ${result.error}`)
    } else {
      if (result.trend != null) priceValue.value = Number(result.trend).toFixed(2)
      if (result.cm_min != null) cmMin.value = Number(result.cm_min).toFixed(2) + '\u20AC'
      if (result.cm_avg != null) cmAvg.value = Number(result.cm_avg).toFixed(2) + '\u20AC'
      if (result.cm_median != null) cmMedian.value = Number(result.cm_median).toFixed(2) + '\u20AC'
      const parts = []
      if (result.trend != null) parts.push(`Trend: ${result.trend.toFixed(2)}\u20AC`)
      if (result.cm_min != null) parts.push(`Min: ${result.cm_min.toFixed(2)}\u20AC`)
      if (result.cm_avg != null) parts.push(`Avg: ${result.cm_avg.toFixed(2)}\u20AC`)
      if (result.cm_median != null) parts.push(`Med: ${result.cm_median.toFixed(2)}\u20AC`)
      showToast(parts.join(' \u00B7 ') || 'No price found')
    }
  } catch (e) {
    console.error(e)
    showToast('Connection error')
  }
  cmRefreshing.value = false
}

async function changeQty(delta) {
  const newQty = Math.max(1, quantity.value + delta)
  try {
    await api.updateCard(props.cardId, { quantity: newQty })
    quantity.value = newQty
    showToast(`Quantity updated: x${newQty}`)
  } catch (e) {
    console.error(e)
  }
}

async function deleteCard() {
  if (!confirm('Remove this card from the collection?')) return
  try {
    await api.deleteCard(props.cardId)
    emit('deleted')
    emit('close')
  } catch (e) {
    console.error(e)
  }
}

async function close() {
  await Promise.all(pendingSaves)
  pendingSaves.length = 0
  emit('updated')
  emit('close')
}

// Populate from card when it changes
watch(() => [props.card, props.visible], async ([card, vis]) => {
  if (!card || !vis) return

  editRarity.value = card.rarity || ''
  editCondition.value = card.condition || ''
  editLang.value = card.lang || ''
  editLocation.value = (card.location || []).join(', ')
  editSetCode.value = card.set_code || ''
  editSetCodeManual.value = card.set_code || ''
  showSetInput.value = false
  quantity.value = card.quantity || 1
  priceValue.value = card.price_cardmarket != null ? Number(card.price_cardmarket).toFixed(2) : ''
  cmMin.value = card.price_cm_min != null ? Number(card.price_cm_min).toFixed(2) + '\u20AC' : '\u2014'
  cmAvg.value = card.price_cm_avg != null ? Number(card.price_cm_avg).toFixed(2) + '\u20AC' : '\u2014'
  cmMedian.value = card.price_cm_median != null ? Number(card.price_cm_median).toFixed(2) + '\u20AC' : '\u2014'
  pendingSaves.length = 0

  // Set initial image
  images.value = [{ display: cardImgUrl(card.image_url), raw: card.image_url }]
  currentIndex.value = 0
  currentImage.value = cardImgUrl(card.image_url)

  // Fetch all image variants
  try {
    const resp = await fetch(`https://db.ygoprodeck.com/api/v7/cardinfo.php?name=${encodeURIComponent(card.name)}`)
    if (resp.ok) {
      const data = await resp.json()
      const cardImages = data.data?.[0]?.card_images || []
      if (cardImages.length > 1) {
        images.value = cardImages.map(i => ({ display: cardImgUrl(i.image_url), raw: i.image_url }))
        const idx = images.value.findIndex(i => i.raw === card.image_url)
        currentIndex.value = idx >= 0 ? idx : 0
        currentImage.value = images.value[currentIndex.value].display
      }
    }
  } catch { /* ignore */ }

  // Fetch set code options
  setCodeOptions.value = [{ value: '', label: 'Loading...', style: '' }]
  try {
    const resp = await fetch(`https://db.ygoprodeck.com/api/v7/cardinfo.php?id=${card.card_id}`)
    if (resp.ok) {
      const apiSets = (await resp.json()).data?.[0]?.card_sets || []
      apiSets.sort((a, b) => (a.set_code || '').localeCompare(b.set_code || ''))
      const opts = []
      if (card.set_code && !apiSets.some(s => s.set_code === card.set_code)) {
        opts.push({ value: card.set_code, label: card.set_code + ' (current)', style: '' })
      }
      if (!card.set_code) {
        opts.push({ value: '', label: '\u2014 Select \u2014', style: '' })
      }
      for (const s of apiSets) {
        opts.push({ value: s.set_code, label: `${s.set_code} \u2014 ${s.set_rarity}`, style: 'color:#ffb74d' })
      }
      opts.push({ value: '__other__', label: 'Other...', style: '' })
      setCodeOptions.value = opts
      editSetCode.value = card.set_code || ''
    } else {
      showSetInput.value = true
    }
  } catch {
    showSetInput.value = true
  }

  // Auto-fetch price if stale
  if (settings.autoFetchPrices) {
    const PRICE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000
    const priceAge = card.price_updated_at ? Date.now() - new Date(card.price_updated_at).getTime() : Infinity
    if (priceAge > PRICE_MAX_AGE_MS && !card.price_manual) {
      refreshCmPrice()
    }
  }
}, { immediate: true })
</script>
