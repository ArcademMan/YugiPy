<template>
  <img
    v-if="flagCode"
    :src="'/flags/' + flagCode + '.png'"
    :alt="lang"
    :title="lang"
    class="lang-flag"
  >
  <span v-else>{{ lang }}</span>
</template>

<script setup>
import { computed } from 'vue'
import { LANG_FLAGS } from '../utils/constants.js'

const props = defineProps({
  lang: { type: String, default: '' }
})

const flagCode = computed(() => LANG_FLAGS[props.lang?.toUpperCase()] || null)
</script>
