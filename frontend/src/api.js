const API = ''

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, options)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
}

function put(path, body) {
  return request(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
}

export default {
  // Cards
  getCards(params = {}) {
    const qs = new URLSearchParams(params).toString()
    return request(`/api/cards${qs ? '?' + qs : ''}`)
  },
  getCard(id) {
    return request(`/api/cards/${id}`)
  },
  updateCard(id, data) {
    return put(`/api/cards/${id}`, data)
  },
  deleteCard(id) {
    return request(`/api/cards/${id}`, { method: 'DELETE' })
  },
  addCard(payload) {
    return post('/api/cards', payload)
  },
  splitCard(id, data) {
    return post(`/api/cards/${id}/split`, data)
  },
  getCardCmPrice(id) {
    return post(`/api/cards/${id}/cm-price`)
  },

  // Scan
  scanImage(formData) {
    return fetch(`${API}/api/scan`, { method: 'POST', body: formData }).then(r => r.json())
  },
  ocrPreview(formData) {
    return fetch(`${API}/api/ocr-preview`, { method: 'POST', body: formData }).then(r => r.json())
  },

  // Search
  searchCards(query) {
    return request(`/api/search?q=${encodeURIComponent(query)}`)
  },

  // Stats
  getStats() {
    return request('/api/stats')
  },

  // Settings
  getSettings() {
    return request('/api/settings')
  },
  updateSettings(data) {
    return put('/api/settings', data)
  },

  // Setup
  getSetupStatus() {
    return request('/api/settings/status')
  },
  cancelSetup() {
    return post('/api/setup/cancel')
  },
  // runSetup and downloadImages use EventSource, handled in composable

  // Extension
  getExtensionStatus() {
    return request('/api/extension/status')
  },

  // Cardmarket Bulk Sync
  startBulkSync() {
    return post('/api/cm-bulk/start')
  },
  stopBulkSync() {
    return post('/api/cm-bulk/stop')
  },
  resumeBulkSync() {
    return post('/api/cm-bulk/resume')
  },
  getBulkStatus() {
    return request('/api/cm-bulk/status')
  },

  // Storage
  getStorageStats() {
    return request('/api/storage/stats')
  },
  openDataFolder() {
    return post('/api/storage/open-folder')
  },
  createBackup() {
    return post('/api/storage/backup')
  },
  deleteBackup(name) {
    return request(`/api/storage/backup/${encodeURIComponent(name)}`, { method: 'DELETE' })
  },
  restoreBackup(file) {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${API}/api/storage/restore`, { method: 'POST', body: form }).then(r => r.json())
  }
}
