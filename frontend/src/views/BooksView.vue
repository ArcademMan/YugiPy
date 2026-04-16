<template>
  <section>
    <div class="page-header">
      <h1>Books</h1>
      <button class="btn-primary" @click="showCreate = true">+ New Book</button>
    </div>

    <div class="books-grid" v-if="booksStore.books.length">
      <div
        class="book-card"
        v-for="book in booksStore.books"
        :key="book.id"
        @click="$router.push(`/books/${book.id}`)"
      >
        <div class="book-card-name">{{ book.name }}</div>
        <div class="book-card-info">
          <span>{{ book.page_count }} pages &middot; {{ book.grid_size }}</span>
          <span>{{ book.assigned_cards }} cards &middot; {{ book.total_slots }} slots</span>
        </div>
        <div class="book-card-bar">
          <div class="book-card-fill" :style="{ width: fillPercent(book) + '%' }"></div>
        </div>
        <div class="book-card-actions">
          <button class="btn-secondary btn-sm" @click.stop="editBook(book)">Edit</button>
          <button class="btn-danger btn-sm" @click.stop="confirmDelete(book)">Delete</button>
        </div>
      </div>
    </div>
    <p v-else class="empty-state">No books yet. Create one to start organizing your collection.</p>

    <div class="books-preview-link" v-if="booksStore.books.length">
      <router-link to="/book" class="btn-secondary">Open full collection preview</router-link>
    </div>

    <!-- Create/Edit Modal -->
    <div class="modal" :hidden="!(showCreate || editingBook)">
      <div class="modal-backdrop" @click="closeModal"></div>
      <div class="modal-content">
        <h2>{{ editingBook ? 'Edit Book' : 'New Book' }}</h2>
        <div class="form-group">
          <label>Name</label>
          <input v-model="form.name" type="text" placeholder="Binder Blu" style="width:100%">
        </div>
        <div class="form-group">
          <label>Pages</label>
          <input v-model.number="form.page_count" type="number" min="1" max="500" style="width:100%">
        </div>
        <div class="form-group">
          <label>Cards per page</label>
          <select v-model="form.grid_size" style="width:100%">
            <option value="3x3">3&times;3 (9)</option>
            <option value="4x3">4&times;3 (12)</option>
            <option value="4x4">4&times;4 (16)</option>
            <option value="5x4">5&times;4 (20)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Group by</label>
          <select v-model="form.group_by" style="width:100%">
            <option value="set">Set</option>
            <option value="archetype">Archetype</option>
            <option value="type">Type</option>
            <option value="none">None</option>
          </select>
        </div>
        <div class="form-group">
          <label>Max copies per card</label>
          <select v-model="form.max_copies" style="width:100%">
            <option :value="0">All</option>
            <option :value="1">1</option>
            <option :value="2">2</option>
            <option :value="3">3</option>
            <option :value="4">4</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="closeModal">Cancel</button>
          <button class="btn-primary" @click="saveBook" :disabled="!form.name.trim()">
            {{ editingBook ? 'Save' : 'Create' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete confirm -->
    <div class="modal" :hidden="!deletingBook">
      <div class="modal-backdrop" @click="deletingBook = null"></div>
      <div class="modal-content">
        <h2>Delete "{{ deletingBook?.name }}"?</h2>
        <p>All card assignments and pins will be removed.</p>
        <div class="modal-actions">
          <button class="btn-secondary" @click="deletingBook = null">Cancel</button>
          <button class="btn-danger" @click="doDelete">Delete</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useBooksStore } from '../stores/books.js'

const booksStore = useBooksStore()

const showCreate = ref(false)
const editingBook = ref(null)
const deletingBook = ref(null)

const defaultForm = () => ({
  name: '',
  page_count: 20,
  grid_size: '3x3',
  group_by: 'archetype',
  max_copies: 0,
})
const form = ref(defaultForm())

function fillPercent(book) {
  if (!book.total_slots) return 0
  return Math.min(100, Math.round((book.assigned_cards / book.total_slots) * 100))
}

function editBook(book) {
  editingBook.value = book
  form.value = {
    name: book.name,
    page_count: book.page_count,
    grid_size: book.grid_size,
    group_by: book.group_by,
    max_copies: book.max_copies,
  }
}

function closeModal() {
  showCreate.value = false
  editingBook.value = null
  form.value = defaultForm()
}

async function saveBook() {
  try {
    if (editingBook.value) {
      await booksStore.updateBook(editingBook.value.id, form.value)
    } else {
      await booksStore.createBook(form.value)
    }
    closeModal()
    await booksStore.loadBooks()
  } catch (e) {
    console.warn('Failed to save book:', e)
  }
}

function confirmDelete(book) {
  deletingBook.value = book
}

async function doDelete() {
  try {
    await booksStore.deleteBook(deletingBook.value.id)
    deletingBook.value = null
  } catch (e) {
    console.warn('Failed to delete book:', e)
  }
}

onMounted(() => booksStore.loadBooks())
</script>
