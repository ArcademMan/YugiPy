import { useSettingsStore } from '../stores/settings.js'
import { buildCardmarketUrl } from '../utils/price.js'

export function useCardmarket() {
  const settings = useSettingsStore()

  function buildUrl(cardName, setName, rarity, lang, setCode) {
    return buildCardmarketUrl(
      cardName, setName, rarity, lang, setCode,
      settings.cmExpansions, settings.cmRarities
    )
  }

  return { buildUrl }
}
