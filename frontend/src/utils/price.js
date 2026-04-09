/**
 * Get the display price for a card based on the price display mode.
 * Returns { price: number|null, dot: string }
 *   dot: "cm" = from cardmarket, "fallback" = using fallback source, "" = manual/unknown
 */
export function getDisplayPrice(card, priceDisplayMode = 'cm_median') {
  if (card.price_manual) return { price: card.price_cardmarket, dot: '' }

  const hasTrend = card.price_source === 'cardmarket' && card.price_cardmarket != null
  const cmPrices = {
    cm_min: card.price_cm_min,
    cm_avg: card.price_cm_avg,
    cm_median: card.price_cm_median
  }
  const hasCm = cmPrices[priceDisplayMode] != null

  if (priceDisplayMode === 'trend') {
    if (hasTrend) return { price: card.price_cardmarket, dot: 'cm' }
    for (const k of ['cm_median', 'cm_avg', 'cm_min']) {
      if (cmPrices[k] != null) return { price: cmPrices[k], dot: 'fallback' }
    }
    return { price: card.price_cardmarket, dot: card.price_cardmarket != null ? '' : '' }
  } else {
    if (hasCm) return { price: cmPrices[priceDisplayMode], dot: 'cm' }
    for (const k of ['cm_median', 'cm_avg', 'cm_min']) {
      if (cmPrices[k] != null) return { price: cmPrices[k], dot: 'fallback' }
    }
    if (hasTrend) return { price: card.price_cardmarket, dot: 'fallback' }
    return { price: card.price_cardmarket, dot: card.price_cardmarket != null ? '' : '' }
  }
}

/**
 * Build a Cardmarket search URL for a card.
 */
export function buildCardmarketUrl(cardName, setName, rarity, lang, setCode, cmExpansions, cmRarities) {
  const base = 'https://www.cardmarket.com/en/YuGiOh/Products/Search'
  const params = new URLSearchParams({ searchString: cardName })
  let expId = setName ? findExpansionId(setName, lang, cmExpansions) : null
  if (!expId && setCode) expId = findExpansionByCode(setCode, cmExpansions)
  if (expId) params.set('idExpansion', expId)
  if (rarity && cmRarities[rarity]) params.set('idRarity', cmRarities[rarity])
  return `${base}?${params}`
}

function findExpansionByCode(setCode, cmExpansions) {
  const prefix = setCode.split('-')[0].toUpperCase()
  for (const [cmName, cmId] of Object.entries(cmExpansions)) {
    if (cmName.endsWith(`(${prefix})`)) return cmId
  }
  return null
}

function findExpansionId(setName, lang, cmExpansions) {
  const isOcg = lang && ['JA', 'KO'].includes(lang.toUpperCase())
  if (isOcg) {
    const ocgId = cmExpansions[setName + ' (OCG)']
    if (ocgId) return ocgId
  }
  if (cmExpansions[setName]) return cmExpansions[setName]

  function normalize(n) {
    return n.toLowerCase()
      .replace(/[:\-\u2013\u2014'/]/g, ' ')
      .replace(/\byu gi oh!?\b/g, '')
      .replace(/\bocg\b/g, '')
      .replace(/\s+/g, ' ')
      .trim()
  }

  const queryWords = new Set(normalize(setName).split(/\s+/).filter(Boolean))
  let bestId = null, bestScore = 0
  for (const [cmName, cmId] of Object.entries(cmExpansions)) {
    const hasOcgTag = cmName.includes('(OCG)') || cmName.includes('(Japanese)') || cmName.includes('(Korean)')
    if (hasOcgTag && !isOcg) continue
    if (!hasOcgTag && isOcg) continue
    const cmWords = new Set(normalize(cmName).split(/\s+/).filter(Boolean))
    let common = 0
    for (const w of queryWords) if (cmWords.has(w)) common++
    if (common >= 2) {
      const score = common / Math.max(queryWords.size, cmWords.size)
      if (score > bestScore) { bestScore = score; bestId = cmId }
    }
  }
  return bestScore >= 0.5 ? bestId : null
}
