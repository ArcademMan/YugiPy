<template>
  <div class="modal" :hidden="!visible">
    <div class="modal-backdrop" @click="$emit('close')"></div>
    <div class="modal-content">
      <button class="modal-close" @click="$emit('close')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <div class="modal-body" v-if="card">
        <div class="modal-img-wrapper">
          <button v-show="images.length > 1" class="modal-img-arrow modal-img-arrow-left" @click="switchImg(-1)">&lsaquo;</button>
          <img :src="currentImg" alt="">
          <button v-show="images.length > 1" class="modal-img-arrow modal-img-arrow-right" @click="switchImg(1)">&rsaquo;</button>
          <span v-show="images.length > 1" class="modal-img-counter">{{ imgIndex + 1 }} / {{ images.length }}</span>
        </div>
        <div>
          <p><strong>{{ card.name }}</strong></p>
          <p>{{ card.type }} {{ card.race ? '/ ' + card.race : '' }}</p>
          <p v-if="card.atk != null">ATK: {{ card.atk }} / DEF: {{ card.def_ ?? '?' }}</p>
          <p class="text-muted">Splitting from x{{ card.quantity }}</p>
        </div>
      </div>

      <div v-if="card">
        <div class="form-row">
          <div class="form-group" style="flex:2">
            <label>Rarity</label>
            <select v-model="rarity">
              <option v-for="r in rarityOptions" :key="r" :value="r">{{ r }}</option>
            </select>
          </div>
          <div class="form-group" style="flex:1">
            <label>Set Code</label>
            <select v-if="!showSetInput" v-model="setCode" @change="onSetSelect">
              <option v-for="s in setCodeOptions" :key="s.value" :value="s.value" :style="s.style">{{ s.label }}</option>
            </select>
            <input v-else type="text" v-model="setCodeManual" placeholder="e.g. BLMR-IT065">
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
      </div>

      <div class="modal-actions split-actions" v-if="card">
        <div class="form-group split-qty-group">
          <label>Copies to split</label>
          <input type="number" v-model.number="splitQty" min="1" :max="card.quantity - 1" class="form-input">
        </div>
        <button class="btn-primary btn-sm" @click="confirmSplit">Confirm Split</button>
        <button class="btn-secondary btn-sm" @click="$emit('close')">Cancel</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { RARITY_OPTIONS, CONDITION_OPTIONS, LANG_OPTIONS } from '../utils/constants.js'
import { cardImgUrl } from '../utils/images.js'
import { useToast } from '../composables/useToast.js'
import LangFlag from './LangFlag.vue'
import api from '../api.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  card: { type: Object, default: null }
})

const emit = defineEmits(['close', 'split'])
const { showToast } = useToast()

// Image carousel
const images = ref([])
const imgIndex = ref(0)
const currentImg = ref('')

function switchImg(delta) {
  if (images.value.length <= 1) return
  imgIndex.value = (imgIndex.value + delta + images.value.length) % images.value.length
  currentImg.value = images.value[imgIndex.value].display
}

// Editable fields
const rarity = ref('')
const condition = ref('')
const lang = ref('')
const setCode = ref('')
const setCodeManual = ref('')
const showSetInput = ref(false)
const setCodeOptions = ref([])
const splitQty = ref(1)

const rarityOptions = computed(() => {
  const opts = [...RARITY_OPTIONS]
  if (rarity.value && !opts.includes(rarity.value)) opts.push(rarity.value)
  return opts
})

function onSetSelect() {
  if (setCode.value === '__other__') {
    showSetInput.value = true
    setCodeManual.value = ''
  }
}

async function confirmSplit() {
  if (!props.card) return
  const sc = showSetInput.value ? (setCodeManual.value.trim() || null) : (setCode.value || null)
  const imageUrl = images.value.length ? images.value[imgIndex.value].raw : null
  try {
    await api.splitCard(props.card.id, {
      quantity: splitQty.value,
      rarity: rarity.value,
      condition: condition.value,
      lang: lang.value,
      set_code: sc,
      image_url: imageUrl
    })
    showToast('Card split!')
    emit('split')
    emit('close')
  } catch (e) {
    console.error(e)
    alert('Error splitting card')
  }
}

watch(() => [props.card, props.visible], async ([card, vis]) => {
  if (!card || !vis) return

  rarity.value = card.rarity || ''
  condition.value = card.condition || ''
  lang.value = card.lang || ''
  setCode.value = card.set_code || ''
  setCodeManual.value = card.set_code || ''
  showSetInput.value = false
  splitQty.value = 1

  images.value = [{ display: cardImgUrl(card.image_url), raw: card.image_url }]
  imgIndex.value = 0
  currentImg.value = cardImgUrl(card.image_url)

  // Fetch image variants
  try {
    const resp = await fetch(`https://db.ygoprodeck.com/api/v7/cardinfo.php?name=${encodeURIComponent(card.name)}`)
    if (resp.ok) {
      const data = await resp.json()
      const ci = data.data?.[0]?.card_images || []
      if (ci.length > 1) {
        images.value = ci.map(i => ({ display: cardImgUrl(i.image_url), raw: i.image_url }))
        const idx = images.value.findIndex(i => i.raw === card.image_url)
        imgIndex.value = idx >= 0 ? idx : 0
        currentImg.value = images.value[imgIndex.value].display
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
      setCode.value = card.set_code || ''
    } else {
      showSetInput.value = true
    }
  } catch {
    showSetInput.value = true
  }
}, { immediate: true })
</script>
