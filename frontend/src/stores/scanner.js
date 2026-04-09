import { defineStore } from 'pinia'

export const useScannerStore = defineStore('scanner', {
  state: () => ({
    scanResults: [],
    extractedText: '',
    lastScanCrop: null
  }),

  actions: {
    setScanResults(results, text = '') {
      this.scanResults = results
      this.extractedText = text
    },

    clear() {
      this.scanResults = []
      this.extractedText = ''
      this.lastScanCrop = null
    }
  }
})
