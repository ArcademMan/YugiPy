/**
 * Convert a YGOProDeck image URL to the local API proxy URL.
 */
export function cardImgUrl(url) {
  if (!url) return ''
  const match = url.match(/\/(\d+)\.\w+$/)
  return match ? `/api/cards/img/${match[1]}` : url
}

/**
 * Detect language code from a set code like "BLMR-IT065".
 * Returns two-letter code (IT, EN, FR, ...) or null.
 */
export function detectLangFromSetCode(setCode) {
  if (!setCode) return null
  const match = setCode.match(/-([A-Z]{2})\d/)
  if (match) {
    const lang = match[1]
    const valid = ['IT', 'EN', 'FR', 'DE', 'ES', 'PT', 'JA', 'KO']
    if (valid.includes(lang)) return lang
  }
  return null
}
