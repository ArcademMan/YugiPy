import { defineStore } from 'pinia'
import api from '../api.js'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    settings: {},
    priceDisplayMode: 'cm_median',
    autoFetchPrices: true,
    cmExpansions: [],
    cmRarities: {}
  }),

  actions: {
    async loadSettings() {
      try {
        const data = await api.getSettings()
        this.settings = data
        if (data.price_display) this.priceDisplayMode = data.price_display
        if (data.auto_fetch_prices !== undefined) this.autoFetchPrices = data.auto_fetch_prices
      } catch (e) {
        console.warn('Failed to load settings:', e)
      }

      // Load Cardmarket mapping data
      try {
        const [exp, rar] = await Promise.all([
          import('../data/cardmarket_expansions.json'),
          import('../data/cardmarket_rarities.json')
        ])
        this.cmExpansions = exp.default || exp
        this.cmRarities = rar.default || rar
      } catch (e) {
        console.warn('Failed to load CM maps:', e)
      }
    },

    async saveSetting(key, value) {
      this.settings[key] = value
      try {
        await api.updateSettings({ [key]: value })
      } catch (e) {
        console.warn('Failed to save setting:', e)
      }
    },

    setPriceDisplayMode(mode) {
      this.priceDisplayMode = mode
      this.saveSetting('price_display', mode)
    },

    setAutoFetchPrices(val) {
      this.autoFetchPrices = val
      this.saveSetting('auto_fetch_prices', val)
    }
  }
})
