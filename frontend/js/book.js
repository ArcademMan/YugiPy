// =============================================
// Book view — binder-style layout
// =============================================

import {
    API, allCollectionCards, setAllCollectionCards,
    RARITY_ORDER, TYPE_GROUP, TYPE_ORDER,
    cardImgUrl, getDisplayPrice, saveSetting, _settings,
} from "./shared.js";
import { openCardModal } from "./collection.js";

let bookPages = [];
let bookCurrentSpread = 0;

export function loadBook() {
    if (allCollectionCards.length > 0) {
        buildAndRenderBook();
    } else {
        fetch(`${API}/api/cards`)
            .then((r) => r.json())
            .then((cards) => {
                setAllCollectionCards(cards);
                buildAndRenderBook();
            })
            .catch((e) => console.error("Failed to load book:", e));
    }
}

function buildAndRenderBook() {
    const setSelect = document.getElementById("book-filter-set");
    const currentSet = setSelect.value;
    const sets = [...new Set(allCollectionCards.map(c => c.set_code ? c.set_code.split("-")[0] : "").filter(Boolean))].sort();
    setSelect.innerHTML = '<option value="">All sets</option>';
    sets.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = s;
        if (s === currentSet) opt.selected = true;
        setSelect.appendChild(opt);
    });
    buildBookPages();
    bookCurrentSpread = 0;
    renderBookSpread();
}

function buildBookPages() {
    const groupBy = document.getElementById("book-group-by").value;
    const sortBy = document.getElementById("book-sort-by").value;
    const newPagePerGroup = document.getElementById("book-new-page").checked;
    const gridSize = document.getElementById("book-grid-size").value;
    const [cols, rows] = gridSize.split("x").map(Number);
    const slotsPerPage = cols * rows;
    const maxCopies = parseInt(document.getElementById("book-max-copies").value) || 0;
    const filterLang = document.getElementById("book-filter-lang").value;
    const filterCondition = document.getElementById("book-filter-condition").value;
    const filterSet = document.getElementById("book-filter-set").value;
    const minPrice = parseFloat(document.getElementById("book-min-price").value) || 0;

    const CONDITION_RANK = { "Mint": 6, "Near Mint": 5, "Excellent": 4, "Good": 3, "Light Played": 2, "Played": 1, "Poor": 0 };
    const minCondRank = filterCondition ? (CONDITION_RANK[filterCondition] ?? 0) : -1;

    let filtered = allCollectionCards.filter(card => {
        if (filterLang && card.lang !== filterLang) return false;
        if (minCondRank >= 0 && (CONDITION_RANK[card.condition] ?? 0) < minCondRank) return false;
        if (filterSet && !(card.set_code || "").startsWith(filterSet)) return false;
        if (minPrice > 0 && (getDisplayPrice(card).price || 0) < minPrice) return false;
        return true;
    });

    const expanded = [];
    for (const card of filtered) {
        const copies = maxCopies > 0 ? Math.min(card.quantity, maxCopies) : card.quantity;
        for (let i = 0; i < copies; i++) expanded.push(card);
    }

    const groups = new Map();
    for (const card of expanded) {
        let key;
        switch (groupBy) {
            case "set": key = card.set_code ? card.set_code.split("-")[0] : "Other"; break;
            case "archetype": key = card.archetype || "No archetype"; break;
            case "type": key = TYPE_GROUP[card.type] || card.type || "Other"; break;
            default: key = "";
        }
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(card);
    }

    const sortedKeys = [...groups.keys()].sort((a, b) => {
        if (a === "Other" || a === "No archetype") return 1;
        if (b === "Other" || b === "No archetype") return -1;
        if (groupBy === "type") return (TYPE_ORDER[a] ?? 99) - (TYPE_ORDER[b] ?? 99);
        return a.localeCompare(b);
    });

    const sortFn = (a, b) => {
        switch (sortBy) {
            case "rarity": return (RARITY_ORDER[b.rarity] ?? -1) - (RARITY_ORDER[a.rarity] ?? -1);
            case "name": return a.name.localeCompare(b.name);
            case "type":
                const aOrder = TYPE_ORDER[TYPE_GROUP[a.type] || a.type] ?? 99;
                const bOrder = TYPE_ORDER[TYPE_GROUP[b.type] || b.type] ?? 99;
                return aOrder - bOrder || (b.level ?? 0) - (a.level ?? 0) || a.name.localeCompare(b.name);
            case "set_code": return (a.set_code || "").localeCompare(b.set_code || "");
            case "price": return (getDisplayPrice(b).price || 0) - (getDisplayPrice(a).price || 0);
            default: return 0;
        }
    };

    bookPages = [];
    if (groupBy === "none" || !newPagePerGroup) {
        const allCards = [];
        for (const key of sortedKeys) { groups.get(key).sort(sortFn); allCards.push(...groups.get(key)); }
        for (let i = 0; i < allCards.length; i += slotsPerPage) {
            bookPages.push({ group: null, slots: allCards.slice(i, i + slotsPerPage) });
        }
    } else {
        for (const key of sortedKeys) {
            const cards = groups.get(key).sort(sortFn);
            for (let i = 0; i < cards.length; i += slotsPerPage) {
                bookPages.push({ group: key, slots: cards.slice(i, i + slotsPerPage) });
            }
            const lastPage = bookPages[bookPages.length - 1];
            while (lastPage.slots.length < slotsPerPage) lastPage.slots.push(null);
        }
    }

    if (bookPages.length > 0) {
        const lastPage = bookPages[bookPages.length - 1];
        while (lastPage.slots.length < slotsPerPage) lastPage.slots.push(null);
    }

    const totalCards = expanded.length;
    const totalPages = bookPages.length;
    document.getElementById("book-stats").textContent = `${totalCards} cards \u00B7 ${totalPages} pages`;
}

function renderBookSpread() {
    const spread = document.getElementById("book-spread");
    const leftIdx = bookCurrentSpread * 2;
    const rightIdx = leftIdx + 1;
    let html = "";
    if (leftIdx < bookPages.length) html += renderBookPage(bookPages[leftIdx]);
    if (rightIdx < bookPages.length) html += renderBookPage(bookPages[rightIdx]);
    spread.innerHTML = html;

    const totalSpreads = Math.ceil(bookPages.length / 2);
    document.getElementById("book-page-num").textContent =
        bookPages.length > 0 ? `${bookCurrentSpread + 1} / ${totalSpreads}` : "No cards";
    document.getElementById("book-prev").disabled = bookCurrentSpread <= 0;
    document.getElementById("book-next").disabled = bookCurrentSpread >= totalSpreads - 1;

    spread.querySelectorAll(".book-slot[data-id]").forEach((el) => {
        el.addEventListener("click", () => {
            openCardModal(Number(el.dataset.id), allCollectionCards);
        });
    });
}

function renderBookPage(page) {
    const showPrices = document.getElementById("book-show-prices").checked;
    const gridSize = document.getElementById("book-grid-size").value;
    const cols = parseInt(gridSize.split("x")[0]);
    const header = page.group
        ? `<div class="book-page-header" title="${page.group}">${page.group}</div>`
        : "";
    const slots = page.slots
        .map((card) => {
            if (!card) return '<div class="book-slot empty"></div>';
            const priceTag = showPrices ? (() => {
                const { price } = getDisplayPrice(card);
                return price ? `<span class="book-slot-price">${Number(price).toFixed(2)}\u20AC</span>` : "";
            })() : "";
            return `<div class="book-slot" data-id="${card.id}"><img src="${cardImgUrl(card.image_url)}" alt="${card.name}" title="${card.name}&#10;${card.set_code || ""} \u00B7 ${card.rarity} \u00B7 ${card.lang}" loading="lazy">${priceTag}</div>`;
        })
        .join("");
    return `<div class="book-page">${header}<div class="book-page-grid" style="grid-template-columns:repeat(${cols},1fr)">${slots}</div></div>`;
}

// Event listeners
["book-group-by", "book-sort-by", "book-new-page", "book-grid-size", "book-max-copies",
 "book-filter-lang", "book-filter-condition", "book-filter-set", "book-min-price", "book-show-prices"
].forEach(id => {
    document.getElementById(id).addEventListener("change", buildAndRenderBook);
});
document.getElementById("book-min-price").addEventListener("input", buildAndRenderBook);
document.getElementById("book-prev").addEventListener("click", () => {
    if (bookCurrentSpread > 0) { bookCurrentSpread--; renderBookSpread(); }
});
document.getElementById("book-next").addEventListener("click", () => {
    if ((bookCurrentSpread + 1) * 2 < bookPages.length) { bookCurrentSpread++; renderBookSpread(); }
});

// Persist preferences
const BOOK_PREF_IDS = ["book-group-by", "book-sort-by", "book-new-page", "book-grid-size",
    "book-max-copies", "book-filter-lang", "book-filter-condition", "book-filter-set",
    "book-min-price", "book-show-prices"];

function saveBookPrefs() {
    const prefs = {};
    BOOK_PREF_IDS.forEach(id => {
        const el = document.getElementById(id);
        prefs[id] = el.type === "checkbox" ? el.checked : el.value;
    });
    saveSetting("bookPrefs", prefs);
}

export function loadBookPrefs() {
    const prefs = _settings.bookPrefs;
    if (prefs) {
        BOOK_PREF_IDS.forEach(id => {
            const el = document.getElementById(id);
            if (prefs[id] !== undefined) {
                if (el.type === "checkbox") el.checked = prefs[id];
                else el.value = prefs[id];
            }
        });
    }
}

BOOK_PREF_IDS.forEach(id => {
    document.getElementById(id).addEventListener("change", saveBookPrefs);
});
