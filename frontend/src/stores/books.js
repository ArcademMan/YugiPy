import { defineStore } from 'pinia'
import api from '../api.js'

export const useBooksStore = defineStore('books', {
  state: () => ({
    books: [],
    currentBook: null,
    bookCards: [],     // BookCard records for current book
    bookSlots: [],     // BookSlot records for current book
    loading: false,
  }),

  actions: {
    async loadBooks() {
      try {
        this.books = await api.getBooks()
      } catch (e) {
        console.warn('Failed to load books:', e)
      }
    },

    async loadBook(id) {
      try {
        this.currentBook = await api.getBook(id)
        await Promise.all([
          this.loadBookCards(id),
          this.loadBookSlots(id),
        ])
      } catch (e) {
        console.warn('Failed to load book:', e)
      }
    },

    async loadBookCards(bookId) {
      try {
        this.bookCards = await api.getBookCards(bookId)
      } catch (e) {
        console.warn('Failed to load book cards:', e)
      }
    },

    async loadBookSlots(bookId) {
      try {
        this.bookSlots = await api.getBookSlots(bookId)
      } catch (e) {
        console.warn('Failed to load book slots:', e)
      }
    },

    async createBook(data) {
      const book = await api.createBook(data)
      this.books.push(book)
      return book
    },

    async updateBook(id, data) {
      const book = await api.updateBook(id, data)
      const idx = this.books.findIndex(b => b.id === id)
      if (idx >= 0) this.books[idx] = book
      if (this.currentBook?.id === id) this.currentBook = book
      return book
    },

    async deleteBook(id) {
      await api.deleteBook(id)
      this.books = this.books.filter(b => b.id !== id)
      if (this.currentBook?.id === id) this.currentBook = null
    },

    async assignCard(bookId, cardId, quantity = 1) {
      const bc = await api.assignCard(bookId, cardId, quantity)
      await this.loadBookCards(bookId)
      return bc
    },

    async unassignCard(bookId, cardId) {
      await api.unassignCard(bookId, cardId)
      await this.loadBookCards(bookId)
    },

    async autoAssign(bookId) {
      await api.autoAssign(bookId)
      await this.loadBookCards(bookId)
    },

    async pinSlot(bookId, groupKey, position, cardId) {
      const bs = await api.pinSlot(bookId, groupKey, position, cardId)
      await this.loadBookSlots(bookId)
      return bs
    },

    async unpinSlot(bookId, slotId) {
      await api.unpinSlot(bookId, slotId)
      await this.loadBookSlots(bookId)
    },
  },
})
