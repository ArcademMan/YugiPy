<template>
  <section>
    <div class="page-header">
      <h1>Scanner</h1>
    </div>

    <div id="camera-container" ref="cameraContainer">
      <video id="camera-feed" ref="videoEl" autoplay playsinline></video>
      <div id="camera-overlay"><div class="card-guide" ref="guideEl"></div></div>
    </div>

    <div class="ocr-live-preview" v-show="showPreview">
      <div class="ocr-live-zone">
        <span class="zone-dot" :style="{ background: detectDotColor }"></span>
        <span class="zone-text">{{ detectText }}</span>
      </div>
      <div class="ocr-live-zone" style="margin-top:4px">
        <span class="zone-dot" :style="{ background: matchDotColor }"></span>
        <span class="zone-text" style="font-weight:700">{{ matchName }}</span>
        <span :style="{ fontSize: '0.8rem', fontWeight: 600, color: matchConfColor }">{{ matchConfText }}</span>
        <span style="color:var(--green);font-size:0.7rem;margin-left:4px">{{ autoInfo }}</span>
      </div>
      <details class="ocr-debug-details">
        <summary>Debug</summary>
        <div>
          <img v-if="dbgArtwork" :src="dbgArtwork" class="ocr-processed-img detection-debug" alt="Artwork">
          <img v-if="dbgWarped" :src="dbgWarped" class="ocr-processed-img detection-debug" alt="Warped">
          <img v-if="dbgDetect" :src="dbgDetect" class="ocr-processed-img detection-debug" alt="Detection">
          <div v-if="dbgSetCodeImg" style="margin-top:8px">
            <p style="font-size:0.7rem;color:var(--text-muted)">Set code &mdash; raw:</p>
            <img :src="dbgSetCodeImg" style="max-height:40px;width:auto;border:1px solid var(--border);border-radius:4px;background:#fff" alt="Set code raw">
            <p v-if="dbgSetCodeProc" style="font-size:0.7rem;color:var(--text-muted);margin-top:4px">Set code &mdash; processed:</p>
            <img v-if="dbgSetCodeProc" :src="dbgSetCodeProc" style="max-height:40px;width:auto;border:1px solid var(--border);border-radius:4px;background:#fff" alt="Set code processed">
            <p style="font-size:0.8rem;font-weight:600;margin-top:4px">{{ dbgSetCodeText }}</p>
          </div>
        </div>
      </details>
    </div>

    <div class="scanner-controls">
      <span class="rotation-label">Card orientation:</span>
      <div class="rotation-buttons">
        <button
          v-for="r in rotations"
          :key="r.value"
          class="rot-btn"
          :class="{ active: rotation === r.value }"
          :title="r.title"
          @click="setRotation(r.value)"
          v-html="r.icon"
        ></button>
      </div>
    </div>

    <button v-show="showCaptureBtn" class="btn-primary btn-capture" @click="capture">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="13" r="4"/><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/></svg>
      Scan
    </button>
    <canvas ref="captureCanvas" hidden></canvas>

    <div class="loading-state" v-show="scanning">
      <div class="spinner"></div>
      <p>Analyzing...</p>
    </div>

    <!-- Add card modal for single-match fast path -->
    <AddCardModal
      :visible="addModalVisible"
      :cardData="addCardData"
      :sets="addCardSets"
      @close="onAddClose"
      @added="onCardAdded"
    />
  </section>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useScannerStore } from '../stores/scanner.js'
import { useToast } from '../composables/useToast.js'
import { cardImgUrl } from '../utils/images.js'
import AddCardModal from '../components/AddCardModal.vue'
import api from '../api.js'

const router = useRouter()
const scannerStore = useScannerStore()
const { showToast } = useToast()

// Refs
const videoEl = ref(null)
const cameraContainer = ref(null)
const guideEl = ref(null)
const captureCanvas = ref(null)

// State
const showPreview = ref(true)
const showCaptureBtn = ref(true)
const scanning = ref(false)
const rotation = ref(0)

// Preview state
const detectDotColor = ref('')
const detectText = ref('Starting camera...')
const matchDotColor = ref('transparent')
const matchName = ref('')
const matchConfText = ref('')
const matchConfColor = ref('')
const autoInfo = ref('')

// Debug
const dbgArtwork = ref(null)
const dbgWarped = ref(null)
const dbgDetect = ref(null)
const dbgSetCodeImg = ref(null)
const dbgSetCodeProc = ref(null)
const dbgSetCodeText = ref('')

// Add modal
const addModalVisible = ref(false)
const addCardData = ref(null)
const addCardSets = ref([])

// Constants
const AUTO_SCAN_THRESHOLD = 0.60
const AUTO_SCAN_FRAMES = 4
const NO_CARD_GRACE = 3
const CARD_RATIO = 59 / 86
const GUIDE_WIDTH_FRAC = 0.55

const rotations = [
  { value: 0, title: 'Card top facing up', icon: '&#x2191;' },
  { value: 270, title: 'Card top facing right', icon: '&#x2192;' },
  { value: 180, title: 'Card top facing down', icon: '&#x2193;' },
  { value: 90, title: 'Card top facing left', icon: '&#x2190;' }
]

// Internal state
let currentStream = null
let previewInterval = null
let previewBusy = false
let autoScanName = ''
let autoScanCount = 0
let autoScanTriggered = false
let lastDetectedMode = 'no_card'
let noCardFrames = 0

function setRotation(val) {
  rotation.value = val
  autoScanName = ''
  autoScanCount = 0
  autoScanTriggered = false
}

function updateGuideOverlay() {
  const video = videoEl.value
  const guide = guideEl.value
  if (!video || !guide || video.videoWidth === 0) return
  const container = cameraContainer.value
  const cw = container.clientWidth, ch = container.clientHeight
  const vw = video.videoWidth, vh = video.videoHeight
  const videoAspect = vw / vh, containerAspect = cw / ch
  let displayW, displayH, offsetX, offsetY
  if (videoAspect > containerAspect) {
    displayW = cw; displayH = cw / videoAspect; offsetX = 0; offsetY = (ch - displayH) / 2
  } else {
    displayH = ch; displayW = ch * videoAspect; offsetX = (cw - displayW) / 2; offsetY = 0
  }
  let guideW = displayW * GUIDE_WIDTH_FRAC, guideH = guideW / CARD_RATIO
  if (guideH > displayH * 0.85) { guideH = displayH * 0.85; guideW = guideH * CARD_RATIO }
  guide.style.width = guideW + 'px'
  guide.style.height = guideH + 'px'
  guide.style.left = (offsetX + (displayW - guideW) / 2) + 'px'
  guide.style.top = (offsetY + (displayH - guideH) / 2) + 'px'
}

function cropGuideRegion() {
  const video = videoEl.value
  const vw = video.videoWidth, vh = video.videoHeight
  let cropW = Math.round(vw * GUIDE_WIDTH_FRAC), cropH = Math.round(cropW / CARD_RATIO)
  if (cropH > vh * 0.9) { cropH = Math.round(vh * 0.85); cropW = Math.round(cropH * CARD_RATIO) }
  const cropX = Math.round((vw - cropW) / 2), cropY = Math.round((vh - cropH) / 2)
  const c = document.createElement('canvas')
  c.width = cropW; c.height = cropH
  c.getContext('2d').drawImage(video, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH)
  return c
}

async function startCamera() {
  if (currentStream) { startPreviewLoop(); return }
  try {
    currentStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }
    })
    const video = videoEl.value
    video.srcObject = currentStream
    video.addEventListener('loadedmetadata', () => {
      const isPortrait = window.innerHeight > window.innerWidth
      const videoLandscape = video.videoWidth > video.videoHeight
      if (isPortrait && videoLandscape) {
        video.classList.add('video-rotate-fix')
        const scale = cameraContainer.value.clientWidth / video.videoHeight
        cameraContainer.value.style.height = Math.round(video.videoWidth * scale) + 'px'
      } else {
        video.classList.remove('video-rotate-fix')
        cameraContainer.value.style.height = ''
      }
      requestAnimationFrame(updateGuideOverlay)
    }, { once: true })
    startPreviewLoop()
  } catch (e) {
    console.error('Camera error:', e)
    alert('Unable to access the camera. Please check permissions.')
  }
}

function stopCamera() {
  stopPreviewLoop()
  if (currentStream) {
    currentStream.getTracks().forEach(t => t.stop())
    currentStream = null
  }
}

function startPreviewLoop() {
  stopPreviewLoop()
  previewBusy = false
  showPreview.value = true
  previewInterval = setInterval(() => {
    if (previewBusy) return
    previewBusy = true
    sendPreviewFrame().finally(() => { previewBusy = false })
  }, 200)
}

function stopPreviewLoop() {
  if (previewInterval) { clearInterval(previewInterval); previewInterval = null }
}

async function sendPreviewFrame() {
  const video = videoEl.value
  if (!video || video.videoWidth === 0) return
  const c = cropGuideRegion()
  const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.85))
  if (!blob) return
  const form = new FormData()
  form.append('file', blob, 'preview.jpg')
  form.append('rotation', rotation.value)
  try {
    const data = await api.ocrPreview(form)
    renderPreview(data)
  } catch { /* ignore */ }
}

function renderPreview(data) {
  if (data.mode === 'no_card' || data.mode === 'no_image') {
    noCardFrames++
    autoScanName = ''; autoScanCount = 0
    if (noCardFrames < NO_CARD_GRACE && lastDetectedMode === 'detected') return
    lastDetectedMode = 'no_card'
    detectDotColor.value = 'var(--red)'
    detectText.value = 'No card detected'
    matchDotColor.value = 'transparent'; matchName.value = ''; matchConfText.value = ''; autoInfo.value = ''
    updateDebug(data)
    return
  }
  noCardFrames = 0; lastDetectedMode = 'detected'
  detectDotColor.value = 'var(--green)'; detectText.value = 'Card detected'
  const hasHash = data.hash_match_name && data.hash_match_name.length > 0
  const conf = data.hash_match_confidence || 0
  if (hasHash) {
    const confColor = conf > 0.7 ? 'var(--green)' : conf > 0.4 ? 'var(--yellow)' : 'var(--red)'
    matchDotColor.value = confColor; matchName.value = data.hash_match_name
    matchConfText.value = `${(conf * 100).toFixed(0)}%`; matchConfColor.value = confColor
    if (conf >= AUTO_SCAN_THRESHOLD && !autoScanTriggered) {
      if (data.hash_match_name === autoScanName) autoScanCount++
      else { autoScanName = data.hash_match_name; autoScanCount = 1 }
      autoInfo.value = autoScanCount > 0 ? `Auto ${autoScanCount}/${AUTO_SCAN_FRAMES}` : ''
      if (autoScanCount >= AUTO_SCAN_FRAMES) { autoScanTriggered = true; capture(); return }
    } else if (conf < AUTO_SCAN_THRESHOLD) { autoScanName = ''; autoScanCount = 0; autoInfo.value = '' }
  } else {
    matchDotColor.value = 'var(--yellow)'; matchName.value = 'No match'; matchConfText.value = ''; autoInfo.value = ''
    autoScanName = ''; autoScanCount = 0
  }
  updateDebug(data)
}

function updateDebug(data) {
  dbgArtwork.value = data.artwork_debug ? 'data:image/jpeg;base64,' + data.artwork_debug : null
  dbgWarped.value = data.warped_image ? 'data:image/jpeg;base64,' + data.warped_image : null
  dbgDetect.value = data.debug_image ? 'data:image/jpeg;base64,' + data.debug_image : null
  if (data.set_code_img) {
    dbgSetCodeImg.value = 'data:image/jpeg;base64,' + data.set_code_img
    dbgSetCodeProc.value = data.set_code_processed ? 'data:image/jpeg;base64,' + data.set_code_processed : null
    dbgSetCodeText.value = 'OCR: ' + (data.set_code_ocr || data.set_code_raw || '(no text)')
  } else { dbgSetCodeImg.value = null }
}

async function capture() {
  stopPreviewLoop()
  const cropped = cropGuideRegion()
  showCaptureBtn.value = false; showPreview.value = false; scanning.value = true
  cropped.toBlob(async (blob) => {
    scannerStore.lastScanCrop = blob
    const form = new FormData()
    form.append('file', blob, 'scan.jpg')
    form.append('rotation', rotation.value)
    try {
      const data = await api.scanImage(form)
      scanning.value = false
      if (data.detail) { alert(data.detail); resetScanner(); return }
      // Single high-confidence match: open add modal directly
      if (data.candidates.length === 1 && data.extracted_text.includes('Image Match')) {
        const card = data.candidates[0]
        const cardForAdd = { ...card }; const sets = card.sets || []; delete cardForAdd.sets
        addCardData.value = cardForAdd; addCardSets.value = sets; addModalVisible.value = true
        return
      }
      // Multiple results: navigate to results view
      scannerStore.setScanResults(data.candidates, data.extracted_text)
      stopCamera()
      router.push('/results')
    } catch (e) {
      console.error(e); scanning.value = false; alert('Server connection error'); resetScanner()
    }
  }, 'image/png')
}

function resetScanner() {
  showCaptureBtn.value = true; showPreview.value = true; scanning.value = false
  autoScanName = ''; autoScanCount = 0; autoScanTriggered = false; noCardFrames = 0
  lastDetectedMode = 'no_card'
  detectText.value = 'Starting camera...'; detectDotColor.value = ''
  matchName.value = ''; matchConfText.value = ''; matchDotColor.value = 'transparent'; autoInfo.value = ''
  startCamera()
}

function onAddClose() {
  addModalVisible.value = false
  resetScanner()
}

function onCardAdded() {
  addModalVisible.value = false
  resetScanner()
}

onMounted(() => startCamera())
onUnmounted(() => stopCamera())
</script>
