<template>
  <section>
    <div class="page-header">
      <h1>Settings</h1>
    </div>

    <!-- Price Settings -->
    <div class="settings-card">
      <div class="settings-card-header">
        <h3>Prices</h3>
      </div>
      <div class="settings-card-body">
        <div class="form-group" style="margin-bottom:12px">
          <label>Price displayed in collection</label>
          <select v-model="priceDisplay" @change="onPriceDisplayChange">
            <option value="trend">Trend (Cardmarket)</option>
            <option value="cm_min">Lowest offer</option>
            <option value="cm_avg">Average of first 5 offers</option>
            <option value="cm_median">Median of first 5 offers</option>
          </select>
        </div>
        <div class="form-group" style="margin-bottom:12px">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" v-model="autoFetch" @change="onAutoFetchChange">
            Auto-fetch prices from Cardmarket when opening a card
          </label>
        </div>
      </div>
    </div>

    <!-- Defaults -->
    <div class="settings-card">
      <div class="settings-card-header">
        <h3>Defaults</h3>
      </div>
      <div class="settings-card-body">
        <div class="form-group" style="margin-bottom:12px">
          <label>Default language for new cards</label>
          <select v-model="defaultLang" @change="onDefaultLangChange">
            <option v-for="l in LANG_OPTIONS" :key="l.value" :value="l.value">{{ l.label }}</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Image Download -->
    <div class="settings-card">
      <div class="settings-card-header">
        <h3>Card Images</h3>
      </div>
      <div class="settings-card-body">
        <p class="text-muted">Download missing card images for offline use.</p>
        <div style="display:flex;gap:8px;margin-top:10px;align-items:center">
          <button class="btn-primary" @click="startImgDownload" :disabled="imgDownloading">{{ imgDownloading ? 'Downloading...' : 'Download missing images' }}</button>
        </div>
        <div v-if="imgDownloading" style="margin-top:12px">
          <div class="progress-bar-container">
            <div class="progress-bar-fill" :style="{ width: imgBarWidth }"></div>
          </div>
          <p class="text-muted" style="margin-top:6px">{{ imgStatus }}</p>
        </div>
      </div>
    </div>

    <!-- Storage & Backup -->
    <div class="settings-card">
      <div class="settings-card-header">
        <h3>Storage &amp; Backup</h3>
      </div>
      <div class="settings-card-body">
        <!-- Stats -->
        <div v-if="storageStats" class="storage-stats-grid">
          <div class="storage-stat">
            <span class="storage-stat-value">{{ storageStats.total_images.toLocaleString() }}</span>
            <span class="storage-stat-label">Images</span>
          </div>
          <div class="storage-stat">
            <span class="storage-stat-value">{{ formatSize(storageStats.total_images_size) }}</span>
            <span class="storage-stat-label">Images size</span>
          </div>
          <div class="storage-stat">
            <span class="storage-stat-value">{{ formatSize(storageStats.db_size) }}</span>
            <span class="storage-stat-label">Database</span>
          </div>
        </div>

        <!-- Data folder -->
        <div style="margin-top:14px">
          <p class="text-muted" style="font-size:0.85rem;word-break:break-all">{{ storageStats?.data_dir || '...' }}</p>
          <button class="btn-secondary btn-sm" style="margin-top:6px" @click="openFolder">Open data folder</button>
        </div>

        <!-- Backup -->
        <div style="margin-top:18px;border-top:1px solid var(--border);padding-top:14px">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <button class="btn-primary" @click="createBackup" :disabled="backupBusy">{{ backupBusy ? 'Creating...' : 'Create backup' }}</button>
            <label class="btn-secondary btn-sm" style="cursor:pointer;margin:0">
              Restore backup
              <input type="file" accept=".zip" hidden @change="onRestoreFile">
            </label>
          </div>
        </div>

        <!-- Backup list -->
        <div v-if="backups.length > 0" style="margin-top:14px">
          <p class="text-muted" style="font-size:0.85rem;margin-bottom:6px">Saved backups:</p>
          <div v-for="b in backups" :key="b.name" class="backup-row">
            <div class="backup-info">
              <span class="backup-name">{{ b.name }}</span>
              <span class="text-muted" style="font-size:0.78rem">{{ formatSize(b.size) }} &mdash; {{ formatDate(b.created) }}</span>
            </div>
            <div class="backup-actions">
              <button class="btn-danger btn-sm" @click="deleteBackup(b.name)">Delete</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useSettingsStore } from '../stores/settings.js'
import { LANG_OPTIONS } from '../utils/constants.js'
import { useToast } from '../composables/useToast.js'
import api from '../api.js'

const settings = useSettingsStore()
const { showToast } = useToast()

// Price settings
const priceDisplay = ref(settings.priceDisplayMode)
const autoFetch = ref(settings.autoFetchPrices)

// Defaults
const defaultLang = ref(settings.defaultLang)

function onPriceDisplayChange() {
  settings.setPriceDisplayMode(priceDisplay.value)
}
function onAutoFetchChange() {
  settings.setAutoFetchPrices(autoFetch.value)
}
function onDefaultLangChange() {
  settings.setDefaultLang(defaultLang.value)
}

// Image download
const imgDownloading = ref(false)
const imgBarWidth = ref('0%')
const imgStatus = ref('')

function startImgDownload() {
  imgDownloading.value = true
  imgBarWidth.value = '0%'; imgStatus.value = 'Starting...'
  const es = new EventSource('/api/setup/download-images')
  es.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.error) { imgStatus.value = `Error: ${msg.error}`; es.close(); imgDownloading.value = false; return }
    if (msg.type === 'info') imgStatus.value = msg.message
    else if (msg.type === 'progress') {
      imgBarWidth.value = msg.total ? `${((msg.done / msg.total) * 100).toFixed(1)}%` : '0%'
      imgStatus.value = `${msg.done} / ${msg.total} (${msg.ok} ok, ${msg.failed} failed)`
    } else if (msg.type === 'done' || msg.type === 'cancelled') {
      imgStatus.value = msg.message || msg.type; es.close(); imgDownloading.value = false
    }
  }
  es.onerror = () => { es.close(); imgStatus.value = 'Connection lost'; imgDownloading.value = false }
}

// Storage & Backup
const storageStats = ref(null)
const backups = ref([])
const backupBusy = ref(false)

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}

function formatDate(iso) {
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

async function loadStorageStats() {
  try {
    const data = await api.getStorageStats()
    storageStats.value = data
    backups.value = data.backups || []
  } catch (e) { console.error(e) }
}

async function openFolder() {
  try { await api.openDataFolder() } catch (e) { console.error(e) }
}

async function createBackup() {
  backupBusy.value = true
  try {
    const result = await api.createBackup()
    if (result.ok) {
      showToast('Backup created!')
      await loadStorageStats()
    } else {
      showToast('Backup failed')
    }
  } catch (e) { console.error(e); showToast('Backup error') }
  backupBusy.value = false
}

async function deleteBackup(name) {
  if (!confirm(`Delete backup "${name}"?`)) return
  try {
    await api.deleteBackup(name)
    await loadStorageStats()
  } catch (e) { console.error(e) }
}

async function onRestoreFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  if (!confirm('Restore this backup? This will overwrite your current collection database.')) {
    e.target.value = ''
    return
  }
  try {
    const result = await api.restoreBackup(file)
    if (result.ok) {
      showToast('Backup restored! Reload the page to see changes.')
    } else {
      showToast(result.error || 'Restore failed')
    }
  } catch (err) { console.error(err); showToast('Restore error') }
  e.target.value = ''
}

onMounted(loadStorageStats)
</script>

<style scoped>
.storage-stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.storage-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}
.storage-stat-value {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--text);
}
.storage-stat-label {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-top: 2px;
}
.backup-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}
.backup-row:last-child { border-bottom: none; }
.backup-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.backup-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  word-break: break-all;
}
.backup-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.backup-actions a {
  text-decoration: none;
}
</style>
