<template>
  <div class="card-grid">
    <CardGridItem
      v-for="card in cards"
      :key="card.id"
      :card="card"
      @click="$emit('card-click', $event)"
    />
  </div>
</template>

<script setup>
import CardGridItem from './CardGridItem.vue'

defineProps({
  cards: { type: Array, required: true }
})

defineEmits(['card-click'])
</script>
