<template>
  <div class="settings-card">
    <div class="settings-card-header">
      <h3>Card Index</h3>
      <span v-if="badgeText" class="badge" :class="badgeClass">{{ badgeText }}</span>
    </div>
    <div class="settings-card-body">
      <div>
        <p class="text-muted" v-html="statusInfo"></p>
      </div>

      <div v-if="wizardVisible">
        <div style="margin-bottom:14px">
          <div v-for="s in steps" :key="s.num" class="setup-step" :class="s.state">
            <span class="step-icon">{{ s.state === 'done' ? '\u25CF' : s.state === 'active' ? '\u25C9' : '\u25CB' }}</span>
            {{ s.label }}
          </div>
        </div>
        <div class="progress-bar-container" style="margin-bottom:8px">
          <div class="progress-bar-fill" :style="{ width: barWidth, background: barColor }"></div>
        </div>
        <p class="text-muted" style="font-size:0.85rem">{{ progressText }}</p>
      </div>

      <div style="display:flex;gap:8px;margin-top:12px">
        <button v-if="showRunBtn" class="btn-primary" @click="runSetup">Configure index</button>
        <button v-if="showUpdateBtn" class="btn-primary" style="background:#ffa726" @click="runSetup">Update (new cards only)</button>
        <button v-if="showCancelBtn" class="btn-primary" style="background:#e53935" @click="cancelSetup" :disabled="cancelDisabled">{{ cancelText }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useToast } from '../composables/useToast.js'
import api from '../api.js'

const { showToast } = useToast()

const statusInfo = ref('Loading status...')
const badgeText = ref('')
const badgeClass = ref('')
const wizardVisible = ref(false)
const showRunBtn = ref(false)
const showUpdateBtn = ref(false)
const showCancelBtn = ref(false)
const cancelDisabled = ref(false)
const cancelText = ref('Cancel')
const barWidth = ref('0%')
const barColor = ref('#29b6f6')
const progressText = ref('')

const steps = reactive([
  { num: 1, label: 'Download card database', state: '' },
  { num: 2, label: 'Download cropped artworks', state: '' },
  { num: 3, label: 'Download full images', state: '' },
  { num: 4, label: 'Build hash index', state: '' }
])

async function loadStatus() {
  try {
    const s = await api.getSetupStatus()
    if (s.running) {
      statusInfo.value = 'Setup in progress...'
      badgeText.value = ''
      showRunBtn.value = false; showUpdateBtn.value = false
      return
    }
    if (s.ready) {
      badgeText.value = 'Ready'; badgeClass.value = 'badge-ok'
      statusInfo.value = `${s.hash_count.toLocaleString()} cards indexed &middot; ${s.full_images.toLocaleString()} images &middot; ${(s.hash_db_size / 1024 / 1024).toFixed(1)} MB`
      showRunBtn.value = false; showUpdateBtn.value = true
    } else {
      badgeText.value = 'Not configured'; badgeClass.value = 'badge-warn'
      statusInfo.value = 'The card recognition index has not been created yet. Start setup to download images and build the index.'
      showRunBtn.value = true; showUpdateBtn.value = false
    }
  } catch {
    statusInfo.value = 'Error loading status.'
  }
}

function setStepState(stepNum, state) {
  const step = steps.find(s => s.num === stepNum)
  if (step) step.state = state
}

function resetSteps() { steps.forEach(s => s.state = '') }

function runSetup() {
  wizardVisible.value = true
  showRunBtn.value = false; showUpdateBtn.value = false
  showCancelBtn.value = true; badgeText.value = ''
  resetSteps()
  barWidth.value = '0%'; barColor.value = '#29b6f6'; progressText.value = ''

  const evtSource = new EventSource('/api/setup/run')
  let currentStep = 0

  evtSource.onmessage = (e) => {
    const d = JSON.parse(e.data)
    if (d.error) {
      evtSource.close()
      progressText.value = d.error === 'already_running' ? 'Setup already running in another session.' : `Error: ${d.message || d.error}`
      barColor.value = '#e53935'; showCancelBtn.value = false; showRunBtn.value = true
      return
    }
    if (d.type === 'step') {
      if (currentStep > 0) setStepState(currentStep, 'done')
      currentStep = d.step; setStepState(currentStep, 'active'); progressText.value = d.label
    }
    if (d.type === 'info') progressText.value = d.message
    if (d.type === 'progress') {
      if (d.total > 0) {
        barWidth.value = `${Math.round((d.done / d.total) * 100)}%`
        let text = `${d.done}/${d.total}`
        if (d.failed) text += ` (${d.failed} failed)`
        if (d.skipped) text += ` (${d.skipped} skipped)`
        progressText.value = d.message || text
      } else if (d.message) progressText.value = d.message
    }
    if (d.type === 'done') {
      evtSource.close(); setStepState(currentStep, 'done')
      barWidth.value = '100%'; barColor.value = '#4caf50'; progressText.value = 'Setup complete!'
      showCancelBtn.value = false; showToast('Card index configured!')
      setTimeout(() => { wizardVisible.value = false; loadStatus() }, 3000)
    }
    if (d.type === 'cancelled') {
      evtSource.close(); progressText.value = 'Cancelled.'; barColor.value = '#ffa726'
      showCancelBtn.value = false; loadStatus()
    }
  }
  evtSource.onerror = () => {
    evtSource.close(); progressText.value = 'Connection lost.'; barColor.value = '#e53935'
    showCancelBtn.value = false; loadStatus()
  }
}

async function cancelSetup() {
  await api.cancelSetup()
  cancelDisabled.value = true; cancelText.value = 'Cancelling...'
  setTimeout(() => { cancelDisabled.value = false; cancelText.value = 'Cancel' }, 3000)
}

onMounted(loadStatus)
</script>
