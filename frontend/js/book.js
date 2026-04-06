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

// ── Sort-rules UI ──────────────────────────────────────────
const SORT_OPTIONS = [
    { value: "rarity_desc",   label: "Rarity ↓" },
    { value: "rarity_asc",    label: "Rarity ↑" },
    { value: "name_asc",      label: "Name A→Z" },
    { value: "name_desc",     label: "Name Z→A" },
    { value: "type_asc",      label: "Type" },
    { value: "level_desc",    label: "Level ↓" },
    { value: "level_asc",     label: "Level ↑" },
    { value: "set_code_asc",  label: "Set code A→Z" },
    { value: "set_code_desc", label: "Set code Z→A" },
    { value: "price_desc",    label: "Price ↓" },
    { value: "price_asc",     label: "Price ↑" },
    { value: "archetype_asc", label: "Archetype A→Z" },
    { value: "archetype_desc",label: "Archetype Z→A" },
];

let sortRules = ["rarity_desc"];   // default

function renderSortRules() {
    const container = document.getElementById("book-sort-rules");
    container.innerHTML = "";
    sortRules.forEach((rule, idx) => {
        const row = document.createElement("div");
        row.className = "sort-rule-row";
        row.draggable = true;
        row.dataset.idx = idx;

        const grip = document.createElement("span");
        grip.className = "sort-rule-grip";
        grip.textContent = "≡";

        const select = document.createElement("select");
        select.className = "sort-rule-select";
        SORT_OPTIONS.forEach(opt => {
            const o = document.createElement("option");
            o.value = opt.value;
            o.textContent = opt.label;
            if (opt.value === rule) o.selected = true;
            select.appendChild(o);
        });
        select.addEventListener("change", () => {
            sortRules[idx] = select.value;
            saveSortRules();
            buildAndRenderBook();
        });

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "sort-rule-remove";
        removeBtn.textContent = "×";
        removeBtn.title = "Remove rule";
        removeBtn.addEventListener("click", () => {
            sortRules.splice(idx, 1);
            if (sortRules.length === 0) sortRules.push("rarity_desc");
            saveSortRules();
            renderSortRules();
            buildAndRenderBook();
        });

        row.append(grip, select, removeBtn);
        container.appendChild(row);

        // Drag & drop reordering
        row.addEventListener("dragstart", (e) => {
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", String(idx));
            row.classList.add("dragging");
        });
        row.addEventListener("dragend", () => row.classList.remove("dragging"));
        row.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; });
        row.addEventListener("drop", (e) => {
            e.preventDefault();
            const from = parseInt(e.dataTransfer.getData("text/plain"));
            const to = idx;
            if (from === to) return;
            const [moved] = sortRules.splice(from, 1);
            sortRules.splice(to, 0, moved);
            saveSortRules();
            renderSortRules();
            buildAndRenderBook();
        });
    });
}

function saveSortRules() {
    saveSetting("bookSortRules", sortRules);
}

function loadSortRules() {
    const saved = _settings.bookSortRules;
    if (Array.isArray(saved) && saved.length > 0) sortRules = saved;
}

let sortRulesInited = false;
function initSortRulesUI() {
    loadSortRules();
    renderSortRules();
    if (sortRulesInited) return;
    sortRulesInited = true;
    document.getElementById("book-sort-add").addEventListener("click", () => {
        const used = new Set(sortRules);
        const next = SORT_OPTIONS.find(o => !used.has(o.value));
        sortRules.push(next ? next.value : "rarity_desc");
        saveSortRules();
        renderSortRules();
        buildAndRenderBook();
    });
}

export function loadBook() {
    initSortRulesUI();
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

    const copiesMode = document.getElementById("book-copies-mode").value;
    const expanded = [];
    if (maxCopies > 0 && copiesMode === "name") {
        const nameCount = new Map();
        for (const card of filtered) {
            const used = nameCount.get(card.name) || 0;
            const remaining = maxCopies - used;
            if (remaining <= 0) continue;
            const copies = Math.min(card.quantity, remaining);
            nameCount.set(card.name, used + copies);
            for (let i = 0; i < copies; i++) expanded.push(card);
        }
    } else {
        for (const card of filtered) {
            const copies = maxCopies > 0 ? Math.min(card.quantity, maxCopies) : card.quantity;
            for (let i = 0; i < copies; i++) expanded.push(card);
        }
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

    const comparators = {
        rarity_desc: (a, b) => (RARITY_ORDER[b.rarity] ?? -1) - (RARITY_ORDER[a.rarity] ?? -1),
        rarity_asc:  (a, b) => (RARITY_ORDER[a.rarity] ?? -1) - (RARITY_ORDER[b.rarity] ?? -1),
        name_asc:    (a, b) => a.name.localeCompare(b.name),
        name_desc:   (a, b) => b.name.localeCompare(a.name),
        type_asc:    (a, b) => (TYPE_ORDER[TYPE_GROUP[a.type] || a.type] ?? 99) - (TYPE_ORDER[TYPE_GROUP[b.type] || b.type] ?? 99),
        level_desc:  (a, b) => (b.level ?? 0) - (a.level ?? 0),
        level_asc:   (a, b) => (a.level ?? 0) - (b.level ?? 0),
        set_code_asc:  (a, b) => (a.set_code || "").localeCompare(b.set_code || ""),
        set_code_desc: (a, b) => (b.set_code || "").localeCompare(a.set_code || ""),
        price_desc:  (a, b) => (getDisplayPrice(b).price || 0) - (getDisplayPrice(a).price || 0),
        price_asc:   (a, b) => (getDisplayPrice(a).price || 0) - (getDisplayPrice(b).price || 0),
        archetype_asc:  (a, b) => (a.archetype || "").localeCompare(b.archetype || ""),
        archetype_desc: (a, b) => (b.archetype || "").localeCompare(a.archetype || ""),
    };
    const sortFn = (a, b) => {
        for (const rule of sortRules) {
            const cmp = comparators[rule];
            if (!cmp) continue;
            const result = cmp(a, b);
            if (result !== 0) return result;
        }
        return 0;
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

// Mobile settings toggle
document.querySelector(".book-settings-summary")?.addEventListener("click", () => {
    document.querySelector(".book-settings-panel").classList.toggle("open");
});

// Event listeners
["book-group-by", "book-new-page", "book-grid-size", "book-max-copies", "book-copies-mode",
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
const BOOK_PREF_IDS = ["book-group-by", "book-new-page", "book-grid-size",
    "book-max-copies", "book-copies-mode", "book-filter-lang", "book-filter-condition",
    "book-filter-set", "book-min-price", "book-show-prices"];

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
