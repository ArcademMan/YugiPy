<template>
  <div class="modal" :hidden="!visible">
    <div class="modal-backdrop" @click="$emit('close')"></div>
    <div class="modal-content">
      <button class="modal-close" @click="$emit('close')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <div class="add-modal-header">
        <img :src="cardImgUrl(cardData?.image_url)" alt="">
        <div>
          <h3>{{ cardData?.name }}</h3>
          <p class="text-muted">{{ cardData?.type }}</p>
        </div>
      </div>

      <div class="form-group">
        <label>Expansion</label>
        <select v-model="selectedSet" @change="syncRarity">
          <option v-for="s in sortedSets" :key="s.set_code" :value="s" style="color:#ffb74d">
            {{ s.set_code }} &mdash; {{ s.set_name }} ({{ s.set_rarity }}){{ s.set_price ? ` \u2014 ${s.set_price}\u20AC` : '' }}
          </option>
          <option v-if="!sortedSets.length" :value="fallbackSet">No expansion found</option>
        </select>
      </div>

      <div class="form-group">
        <label>Rarity</label>
        <select v-model="rarity">
          <option v-for="r in allRarityOptions" :key="r" :value="r">{{ r }}</option>
        </select>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Condition</label>
          <select v-model="condition">
            <option v-for="c in CONDITION_OPTIONS" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>Language</label>
          <select v-model="lang">
            <option v-for="l in LANG_OPTIONS" :key="l.value" :value="l.value">{{ l.label }}</option>
          </select>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Quantity</label>
          <input type="number" v-model.number="qty" min="1" step="1">
        </div>
        <div class="form-group" style="flex:2">
          <label>Location <span class="text-muted">(optional)</span></label>
          <input type="text" v-model="location" placeholder="e.g. binder, deck blue-eyes...">
        </div>
      </div>

      <button class="btn-primary btn-full" @click="confirm">Add to collection</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { RARITY_OPTIONS, CONDITION_OPTIONS, LANG_OPTIONS } from '../utils/constants.js'
import { cardImgUrl } from '../utils/images.js'
import { detectLangFromSetCode } from '../utils/images.js'
import { useToast } from '../composables/useToast.js'
import api from '../api.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  cardData: { type: Object, default: null },
  sets: { type: Array, default: () => [] }
})

const emit = defineEmits(['close', 'added'])
const { showToast } = useToast()

const fallbackSet = { set_code: 'N/A', set_rarity: 'Common', set_name: 'Unknown', set_price: null }
const sortedSets = computed(() => [...props.sets].sort((a, b) => (a.set_code || '').localeCompare(b.set_code || '')))
const selectedSet = ref(null)
const rarity = ref('Common')
const condition = ref(localStorage.getItem('yugipy_last_condition') || 'Near Mint')
const lang = ref(localStorage.getItem('yugipy_last_lang') || 'IT')
const qty = ref(1)
const location = ref('')

// All rarity options, including current rarity if not in the standard list
const allRarityOptions = computed(() => {
  const opts = [...RARITY_OPTIONS]
  if (rarity.value && !opts.includes(rarity.value)) opts.push(rarity.value)
  return opts
})

function syncRarity() {
  if (selectedSet.value?.set_rarity) {
    rarity.value = selectedSet.value.set_rarity
  }
}

watch(() => props.visible, (val) => {
  if (val && props.sets.length) {
    selectedSet.value = sortedSets.value[0] || fallbackSet
    syncRarity()
    const detectedLang = detectLangFromSetCode(props.sets[0]?.set_code)
    if (detectedLang) lang.value = detectedLang
    else lang.value = localStorage.getItem('yugipy_last_lang') || 'IT'
    condition.value = localStorage.getItem('yugipy_last_condition') || 'Near Mint'
    qty.value = 1
    location.value = ''
  }
})

async function confirm() {
  if (!props.cardData) return
  const set = selectedSet.value || fallbackSet
  const locationArr = location.value.trim() ? location.value.split(',').map(s => s.trim()).filter(Boolean) : null
  const payload = {
    ...props.cardData,
    set_code: (set.set_code && set.set_code !== 'N/A') ? set.set_code : null,
    rarity: rarity.value,
    condition: condition.value,
    lang: lang.value,
    location: locationArr,
    quantity: qty.value
  }
  if (set.set_price && set.set_price > 0) {
    payload.price_cardmarket = set.set_price
  }
  try {
    await api.addCard(payload)
    localStorage.setItem('yugipy_last_lang', lang.value)
    localStorage.setItem('yugipy_last_condition', condition.value)
    showToast('Card added to collection!')
    emit('added')
    emit('close')
  } catch (e) {
    console.error(e)
    alert('Error adding card')
  }
}
</script>
