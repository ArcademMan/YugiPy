<template>
  <nav class="bottom-nav">
    <div class="nav-brand">
      <img src="/assets/icon.png" alt="YugiPy" class="header-logo">
      <span class="header-title">YugiPy</span>
    </div>
    <div class="nav-buttons">
      <router-link
        v-for="item in navItems"
        :key="item.name"
        :to="item.to"
        class="nav-btn"
        active-class="active"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" v-html="item.icon"></svg>
        <span>{{ item.label }}</span>
      </router-link>
    </div>
    <button
      id="ext-status-btn"
      class="ext-status-dot"
      :class="extStatus"
      :title="'Extension: ' + extStatus"
      @click="checkExtension"
    ></button>
  </nav>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../api.js'

const navItems = [
  {
    name: 'collection',
    to: '/',
    label: 'Collection',
    icon: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'
  },
  {
    name: 'scanner',
    to: '/scanner',
    label: 'Scanner',
    icon: '<path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/>'
  },
  {
    name: 'book',
    to: '/book',
    label: 'Book',
    icon: '<path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M4 4.5A2.5 2.5 0 016.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15z"/>'
  },
  {
    name: 'stats',
    to: '/stats',
    label: 'Stats',
    icon: '<path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/>'
  },
  {
    name: 'settings',
    to: '/settings',
    label: 'Settings',
    icon: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>'
  }
]

const extStatus = ref('disconnected')
let pollTimer = null

async function checkExtension() {
  try {
    const res = await api.getExtensionStatus()
    extStatus.value = res.connected ? 'connected' : 'disconnected'
  } catch {
    extStatus.value = 'disconnected'
  }
}

onMounted(() => {
  checkExtension()
  pollTimer = setInterval(checkExtension, 30000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
