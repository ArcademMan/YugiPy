import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'collection',
    component: () => import('./views/CollectionView.vue')
  },
  {
    path: '/scanner',
    name: 'scanner',
    component: () => import('./views/ScannerView.vue')
  },
  {
    path: '/results',
    name: 'results',
    component: () => import('./views/ResultsView.vue')
  },
  {
    path: '/book',
    name: 'book',
    component: () => import('./views/BookView.vue')
  },
  {
    path: '/books',
    name: 'books',
    component: () => import('./views/BooksView.vue')
  },
  {
    path: '/books/:id',
    name: 'book-detail',
    component: () => import('./views/BookDetailView.vue')
  },
  {
    path: '/stats',
    name: 'stats',
    component: () => import('./views/StatsView.vue')
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('./views/SettingsView.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Persist active view to localStorage
router.afterEach((to) => {
  if (to.name) {
    localStorage.setItem('yugipy_activeView', to.name)
  }
})

export default router
