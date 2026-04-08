// =============================================
// Shared state, constants, and utilities
// =============================================

export const API = "";

// --- Shared mutable state ---
export let allCollectionCards = [];
export function setAllCollectionCards(cards) { allCollectionCards = cards; }

export let currentModalCardId = null;
export function setCurrentModalCardId(id) { currentModalCardId = id; }

export let currentModalCard = null;
export function setCurrentModalCard(card) { currentModalCard = card; }

export let pendingModalSaves = [];

// --- Settings ---
export let _settings = {};
export let priceDisplayMode = "cm_median";

export async function loadSettings() {
    try {
        const resp = await fetch(`${API}/api/settings`);
        if (resp.ok) _settings = await resp.json();
    } catch (e) { /* use defaults */ }
    priceDisplayMode = _settings.priceDisplay || "cm_median";
}

export function setPriceDisplayMode(mode) { priceDisplayMode = mode; }

export async function saveSetting(key, value) {
    _settings[key] = value;
    try {
        await fetch(`${API}/api/settings`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ [key]: value }),
        });
    } catch (e) { console.error("Failed to save setting:", e); }
}

// --- Constants ---
export const RARITY_OPTIONS = [
    "Common","Short Print","Rare","Super Rare","Ultra Rare","Secret Rare",
    "Ultimate Rare","Ghost Rare","Gold Rare","Gold Secret Rare","Ghost/Gold Rare",
    "Premium Gold Rare","Collector's Rare","Prismatic Secret Rare","Starlight Rare",
    "Quarter Century Secret Rare","Platinum Secret Rare","Extra Secret Rare",
    "Mosaic Rare","Shatterfoil Rare","Starfoil Rare","Parallel Rare","Special",
    "Duel Terminal Normal Parallel Rare","Duel Terminal Rare Parallel Rare",
    "Duel Terminal Super Parallel Rare","Duel Terminal Ultra Parallel Rare",
    "Super Parallel Rare","Ultra Parallel Rare","Ultra Rare (Pharaoh's Rare)",
    "Millennium Gold Rare", "Millenium Rare",
    "Kaiba Corporation Common", "Kaiba Corporation Rare",
    "Kaiba Corporation Ultra Rare", "Holographic"
];

export const LANG_FLAGS = { IT: "it", EN: "gb", FR: "fr", DE: "de", ES: "es", PT: "pt", JA: "jp", KO: "kr" };

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
    "Token": "Token",
};

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
    "Token": 10,
};

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
    "Platinum Secret Rare": 13,
};

// --- Cardmarket mappings ---
export let CM_EXPANSIONS = {};
export let CM_RARITIES = {};

Promise.all([
    fetch("js/cardmarket_expansions.json").then(r => r.json()),
    fetch("js/cardmarket_rarities.json").then(r => r.json()),
]).then(([exp, rar]) => { CM_EXPANSIONS = exp; CM_RARITIES = rar; })
  .catch(() => console.warn("Cardmarket mappings not loaded"));

// --- Utility functions ---
export function langFlag(lang) {
    const code = LANG_FLAGS[lang?.toUpperCase()];
    return code ? `<img src="/flags/${code}.png" alt="${lang}" title="${lang}" class="lang-flag">` : lang || "";
}

export function cardImgUrl(url) {
    if (!url) return "";
    const match = url.match(/\/(\d+)\.\w+$/);
    return match ? `${API}/api/cards/img/${match[1]}` : url;
}

export function getDisplayPrice(card) {
    if (card.price_manual) return { price: card.price_cardmarket, dot: "" };

    const hasTrend = card.price_source === "cardmarket" && card.price_cardmarket != null;
    const cmPrices = {
        cm_min: card.price_cm_min,
        cm_avg: card.price_cm_avg,
        cm_median: card.price_cm_median,
    };
    const hasCm = cmPrices[priceDisplayMode] != null;

    if (priceDisplayMode === "trend") {
        if (hasTrend) return { price: card.price_cardmarket, dot: "cm" };
        for (const k of ["cm_median", "cm_avg", "cm_min"]) {
            if (cmPrices[k] != null) return { price: cmPrices[k], dot: "fallback" };
        }
        return { price: card.price_cardmarket, dot: card.price_cardmarket != null ? "" : "" };
    } else {
        if (hasCm) return { price: cmPrices[priceDisplayMode], dot: "cm" };
        for (const k of ["cm_median", "cm_avg", "cm_min"]) {
            if (cmPrices[k] != null) return { price: cmPrices[k], dot: "fallback" };
        }
        if (hasTrend) return { price: card.price_cardmarket, dot: "fallback" };
        return { price: card.price_cardmarket, dot: card.price_cardmarket != null ? "" : "" };
    }
}

export function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2200);
}

export function buildCardmarketUrl(cardName, setName, rarity, lang, setCode) {
    const base = "https://www.cardmarket.com/en/YuGiOh/Products/Search";
    const params = new URLSearchParams({ searchString: cardName });
    let expId = setName ? findExpansionId(setName, lang) : null;
    if (!expId && setCode) expId = findExpansionByCode(setCode);
    if (expId) params.set("idExpansion", expId);
    if (rarity && CM_RARITIES[rarity]) params.set("idRarity", CM_RARITIES[rarity]);
    return `${base}?${params}`;
}

function findExpansionByCode(setCode) {
    const prefix = setCode.split("-")[0].toUpperCase();
    for (const [cmName, cmId] of Object.entries(CM_EXPANSIONS)) {
        if (cmName.endsWith(`(${prefix})`)) return cmId;
    }
    return null;
}

function findExpansionId(setName, lang) {
    const isOcg = lang && ["JA", "KO"].includes(lang.toUpperCase());
    if (isOcg) {
        const ocgId = CM_EXPANSIONS[setName + " (OCG)"];
        if (ocgId) return ocgId;
    }
    if (CM_EXPANSIONS[setName]) return CM_EXPANSIONS[setName];
    function normalize(n) { return n.toLowerCase().replace(/[:\-–—'/]/g, " ").replace(/\byu gi oh!?\b/g, "").replace(/\bocg\b/g, "").replace(/\s+/g, " ").trim(); }
    const queryWords = new Set(normalize(setName).split(/\s+/).filter(Boolean));
    let bestId = null, bestScore = 0;
    for (const [cmName, cmId] of Object.entries(CM_EXPANSIONS)) {
        const hasOcgTag = cmName.includes("(OCG)") || cmName.includes("(Japanese)") || cmName.includes("(Korean)");
        if (hasOcgTag && !isOcg) continue;
        if (!hasOcgTag && isOcg) continue;
        const cmWords = new Set(normalize(cmName).split(/\s+/).filter(Boolean));
        let common = 0;
        for (const w of queryWords) if (cmWords.has(w)) common++;
        if (common >= 2) {
            const score = common / Math.max(queryWords.size, cmWords.size);
            if (score > bestScore) { bestScore = score; bestId = cmId; }
        }
    }
    return bestScore >= 0.5 ? bestId : null;
}

export function detectLangFromSetCode(setCode) {
    if (!setCode) return null;
    const match = setCode.match(/-([A-Z]{2})\d/);
    if (match) {
        const lang = match[1];
        const valid = ["IT", "EN", "FR", "DE", "ES", "PT", "JA", "KO"];
        if (valid.includes(lang)) return lang;
    }
    return null;
}
