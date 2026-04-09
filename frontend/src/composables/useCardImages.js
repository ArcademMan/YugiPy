import { ref, watch } from 'vue'
import { cardImgUrl } from '../utils/images.js'

/**
 * Composable for fetching and navigating card image variants from YGOProDeck.
 * @param {Ref<string>} cardName - reactive card name
 * @param {Ref<string>} initialImageUrl - initial image URL
 */
export function useCardImages(cardName, initialImageUrl) {
  const images = ref([])
  const currentIndex = ref(0)
  const currentImage = ref('')

  async function fetchImages(name) {
    if (!name) {
      images.value = []
      currentIndex.value = 0
      currentImage.value = initialImageUrl?.value || ''
      return
    }
    try {
      const resp = await fetch(
        `https://db.ygoprodeck.com/api/v7/cardinfo.php?name=${encodeURIComponent(name)}`
      )
      if (!resp.ok) throw new Error('not found')
      const data = await resp.json()
      const card = data.data?.[0]
      if (card?.card_images) {
        images.value = card.card_images.map(ci => cardImgUrl(ci.image_url))
      } else {
        images.value = []
      }
    } catch {
      images.value = []
    }

    // Find current image index
    const initUrl = initialImageUrl?.value ? cardImgUrl(initialImageUrl.value) : ''
    const idx = images.value.indexOf(initUrl)
    currentIndex.value = idx >= 0 ? idx : 0
    currentImage.value = images.value[currentIndex.value] || initUrl
  }

  function switchImage(delta) {
    if (images.value.length <= 1) return
    currentIndex.value = (currentIndex.value + delta + images.value.length) % images.value.length
    currentImage.value = images.value[currentIndex.value]
  }

  // Auto-fetch when card name changes
  if (cardName) {
    watch(cardName, (name) => fetchImages(name), { immediate: true })
  }

  return { images, currentIndex, currentImage, switchImage, fetchImages }
}
