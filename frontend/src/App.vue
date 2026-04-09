<template>
  <NavBar />
  <main>
    <router-view />
  </main>
  <ToastContainer />
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import NavBar from './components/NavBar.vue'
import ToastContainer from './components/ToastContainer.vue'
import { useSettingsStore } from './stores/settings.js'

const router = useRouter()
const settingsStore = useSettingsStore()

onMounted(async () => {
  await settingsStore.loadSettings()

  // Restore last active view
  const saved = localStorage.getItem('yugipy_activeView')
  if (saved && saved !== 'collection') {
    router.replace({ name: saved }).catch(() => {})
  }
})
</script>
