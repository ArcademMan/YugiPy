import { defineStore } from 'pinia'
import api from '../api.js'

export const useCollectionStore = defineStore('collection', {
  state: () => ({
    allCards: [],
    currentModalCardId: null,
    currentModalCard: null,
    pendingModalSaves: []
  }),

  actions: {
    async loadCollection(params = {}) {
      try {
        const data = await api.getCards(params)
        this.allCards = data
      } catch (e) {
        console.error('Failed to load collection:', e)
      }
    },

    setModalCard(id, card) {
      this.currentModalCardId = id
      this.currentModalCard = card
      this.pendingModalSaves = []
    },

    clearModal() {
      this.currentModalCardId = null
      this.currentModalCard = null
      this.pendingModalSaves = []
    }
  }
})
