// =============================================
// Shared constants — single source of truth
// =============================================

export const RARITY_OPTIONS = [
  "Common", "Short Print", "Rare", "Super Rare", "Ultra Rare", "Secret Rare",
  "Ultimate Rare", "Ghost Rare", "Gold Rare", "Gold Secret Rare", "Ghost/Gold Rare",
  "Premium Gold Rare", "Collector's Rare", "Prismatic Secret Rare", "Starlight Rare",
  "Quarter Century Secret Rare", "Platinum Secret Rare", "Extra Secret Rare",
  "Mosaic Rare", "Shatterfoil Rare", "Starfoil Rare", "Parallel Rare", "Special",
  "Duel Terminal Normal Parallel Rare", "Duel Terminal Rare Parallel Rare",
  "Duel Terminal Super Parallel Rare", "Duel Terminal Ultra Parallel Rare",
  "Super Parallel Rare", "Ultra Parallel Rare", "Ultra Rare (Pharaoh's Rare)",
  "Millennium Gold Rare", "Millenium Rare",
  "Kaiba Corporation Common", "Kaiba Corporation Rare",
  "Kaiba Corporation Ultra Rare", "Holographic"
]

export const LANG_FLAGS = {
  IT: "it", EN: "gb", FR: "fr", DE: "de", ES: "es", PT: "pt", JA: "jp", KO: "kr"
}

export const LANG_OPTIONS = [
  { value: "IT", label: "Italian" },
  { value: "EN", label: "English" },
  { value: "FR", label: "Fran\u00e7ais" },
  { value: "DE", label: "Deutsch" },
  { value: "ES", label: "Espa\u00f1ol" },
  { value: "PT", label: "Portugu\u00eas" },
  { value: "JA", label: "\u65e5\u672c\u8a9e" },
  { value: "KO", label: "\ud55c\uad6d\uc5b4" }
]

export const CONDITION_OPTIONS = [
  { value: "N/A", label: "N/A" },
  { value: "Mint", label: "Mint" },
  { value: "Near Mint", label: "Near Mint" },
  { value: "Excellent", label: "Excellent" },
  { value: "Good", label: "Good" },
  { value: "Light Played", label: "Light Played" },
  { value: "Played", label: "Played" },
  { value: "Poor", label: "Poor" }
]

export const TYPE_GROUP = {
  "Normal Monster": "Normal Monster",
  "Effect Monster": "Effect Monster",
  "Flip Effect Monster": "Effect Monster",
  "Spirit Monster": "Effect Monster",
  "Toon Monster": "Effect Monster",
  "Union Effect Monster": "Effect Monster",
  "Gemini Monster": "Effect Monster",
  "Tuner Monster": "Effect Monster",
  "Pendulum Normal Monster": "Pendulum Monster",
  "Pendulum Effect Monster": "Pendulum Monster",
  "Pendulum Tuner Effect Monster": "Pendulum Monster",
  "Pendulum Flip Effect Monster": "Pendulum Monster",
  "Ritual Monster": "Ritual Monster",
  "Ritual Effect Monster": "Ritual Monster",
  "Fusion Monster": "Fusion Monster",
  "Synchro Monster": "Synchro Monster",
  "Synchro Tuner Monster": "Synchro Monster",
  "Synchro Pendulum Effect Monster": "Synchro Monster",
  "XYZ Monster": "XYZ Monster",
  "XYZ Pendulum Effect Monster": "XYZ Monster",
  "Link Monster": "Link Monster",
  "Spell Card": "Spell",
  "Trap Card": "Trap",
  "Token": "Token"
}

export const TYPE_ORDER = {
  "Normal Monster": 0,
  "Effect Monster": 1,
  "Ritual Monster": 2,
  "Fusion Monster": 3,
  "Synchro Monster": 4,
  "XYZ Monster": 5,
  "Pendulum Monster": 6,
  "Link Monster": 7,
  "Spell": 8,
  "Trap": 9,
  "Token": 10
}

export const RARITY_ORDER = {
  "Common": 0,
  "Short Print": 1,
  "Rare": 2,
  "Starfoil Rare": 2,
  "Mosaic Rare": 2,
  "Shatterfoil Rare": 2,
  "Duel Terminal Normal Parallel Rare": 2,
  "Duel Terminal Rare Parallel Rare": 3,
  "Super Rare": 3,
  "Super Parallel Rare": 3,
  "Duel Terminal Super Parallel Rare": 3,
  "Ultra Rare": 4,
  "Ultra Rare (Pharaoh's Rare)": 4,
  "Duel Terminal Ultra Parallel Rare": 4,
  "Secret Rare": 5,
  "Gold Rare": 5,
  "Gold Secret Rare": 6,
  "Ghost/Gold Rare": 6,
  "Premium Gold Rare": 5,
  "Extra Secret Rare": 6,
  "Ultimate Rare": 7,
  "Ghost Rare": 8,
  "Collector's Rare": 9,
  "Prismatic Secret Rare": 10,
  "Starlight Rare": 11,
  "Quarter Century Secret Rare": 12,
  "Platinum Secret Rare": 13
}

export const CONDITION_RANK = {
  "Mint": 0, "Near Mint": 1, "Excellent": 2, "Good": 3,
  "Light Played": 4, "Played": 5, "Poor": 6
}

export const COND_TAG = {
  "Mint": "M", "Near Mint": "NM", "Excellent": "EX", "Good": "GD",
  "Light Played": "LP", "Played": "PL", "Poor": "PR"
}
