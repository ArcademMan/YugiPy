const API = "";
let currentModalCardId = null;
let pendingModalSaves = [];

// Language code to flag country code mapping
const LANG_FLAGS = { IT: "it", EN: "gb", FR: "fr", DE: "de", ES: "es", PT: "pt", JA: "jp", KO: "kr" };
function langFlag(lang) {
    const code = LANG_FLAGS[lang?.toUpperCase()];
    return code ? `<img src="/flags/${code}.png" alt="${lang}" title="${lang}" class="lang-flag">` : lang || "";
}

// --- Settings (synced with backend) ---
let _settings = {};
let priceDisplayMode = "trend";

async function loadSettings() {
    try {
        const resp = await fetch(`${API}/api/settings`);
        if (resp.ok) _settings = await resp.json();
    } catch (e) { /* use defaults */ }
    priceDisplayMode = _settings.priceDisplay || "trend";
}

async function saveSetting(key, value) {
    _settings[key] = value;
    try {
        await fetch(`${API}/api/settings`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ [key]: value }),
        });
    } catch (e) { console.error("Failed to save setting:", e); }
}

// Returns { price, dot } where dot is "cm" | "fallback" | "" (ygoprodeck/manual)
function getDisplayPrice(card) {
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
        // Fallback to any available CM price
        for (const k of ["cm_median", "cm_avg", "cm_min"]) {
            if (cmPrices[k] != null) return { price: cmPrices[k], dot: "fallback" };
        }
        return { price: card.price_cardmarket, dot: card.price_cardmarket != null ? "" : "" };
    } else {
        // cm_min, cm_avg, or cm_median
        if (hasCm) return { price: cmPrices[priceDisplayMode], dot: "cm" };
        // Fallback: try other CM prices, then trend
        for (const k of ["cm_median", "cm_avg", "cm_min"]) {
            if (cmPrices[k] != null) return { price: cmPrices[k], dot: "fallback" };
        }
        if (hasTrend) return { price: card.price_cardmarket, dot: "fallback" };
        return { price: card.price_cardmarket, dot: card.price_cardmarket != null ? "" : "" };
    }
}

// --- Cardmarket mappings ---
let CM_EXPANSIONS = {};
let CM_RARITIES = {};
Promise.all([
    fetch("js/cardmarket_expansions.json").then(r => r.json()),
    fetch("js/cardmarket_rarities.json").then(r => r.json()),
]).then(([exp, rar]) => { CM_EXPANSIONS = exp; CM_RARITIES = rar; })
  .catch(() => console.warn("Cardmarket mappings not loaded"));

const CM_LANGS = { EN: 1, FR: 2, DE: 3, ES: 4, IT: 5, PT: 6, JA: 7, KO: 8 };

function buildCardmarketUrl(cardName, setName, rarity, lang, setCode) {
    const base = "https://www.cardmarket.com/en/YuGiOh/Products/Search";
    const params = new URLSearchParams({ searchString: cardName });
    let expId = setName ? findExpansionId(setName, lang) : null;
    if (!expId && setCode) expId = findExpansionByCode(setCode);
    if (expId) params.set("idExpansion", expId);
    if (rarity && CM_RARITIES[rarity]) params.set("idRarity", CM_RARITIES[rarity]);
    // Note: language filter omitted from search URL as it can break redirect
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
    // OCG variant
    if (isOcg) {
        const ocgId = CM_EXPANSIONS[setName + " (OCG)"];
        if (ocgId) return ocgId;
    }
    // Exact match
    if (CM_EXPANSIONS[setName]) return CM_EXPANSIONS[setName];
    // Fuzzy match
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

// --- Navigation ---
document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        switchToView(btn.dataset.view);

        if (btn.dataset.view === "scanner") {
            resetScanner();
        } else {
            stopCamera();
            if (btn.dataset.view === "collection") loadCollection();
            if (btn.dataset.view === "book") loadBook();
        }
    });
});

// --- Collection ---
let allCollectionCards = [];

async function loadCollection() {
    try {
        const params = new URLSearchParams();
        const rarity = document.getElementById("filter-rarity").value;
        const condition = document.getElementById("filter-condition").value;
        const lang = document.getElementById("filter-lang").value;
        if (rarity) params.set("rarity", rarity);
        if (condition) params.set("condition", condition);
        if (lang) params.set("lang", lang);

        const resp = await fetch(`${API}/api/cards?${params}`);
        allCollectionCards = await resp.json();
        updateRarityFilter(allCollectionCards);
        applyLocalFilters();
    } catch (e) {
        console.error("Failed to load collection:", e);
    }
}

function updateRarityFilter(cards) {
    const select = document.getElementById("filter-rarity");
    const current = select.value;
    const rarities = [...new Set(cards.map((c) => c.rarity))].sort();
    // Keep first option, rebuild rest
    select.innerHTML = '<option value="">All rarities</option>';
    rarities.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r;
        opt.textContent = r;
        if (r === current) opt.selected = true;
        select.appendChild(opt);
    });
}

// Filter change listeners
["filter-rarity", "filter-condition", "filter-lang"].forEach((id) => {
    document.getElementById(id).addEventListener("change", loadCollection);
});

function applyLocalFilters() {
    const q = document.getElementById("search-input").value.trim().toLowerCase();
    const cards = q
        ? allCollectionCards.filter((c) =>
            c.name.toLowerCase().includes(q) ||
            (c.set_code && c.set_code.toLowerCase().includes(q)))
        : allCollectionCards;
    renderCollection(cards);
}

document.getElementById("sort-select").addEventListener("change", applyLocalFilters);

function renderCollection(cards) {
    window._lastCards = cards;
    const grid = document.getElementById("card-grid");
    const empty = document.getElementById("empty-state");
    const stats = document.getElementById("collection-stats");

    if (cards.length === 0) {
        grid.innerHTML = "";
        empty.hidden = false;
        stats.textContent = "";
        return;
    }

    empty.hidden = true;
    const totalCards = cards.reduce((sum, c) => sum + c.quantity, 0);
    const totalValue = cards.reduce((sum, c) => sum + (getDisplayPrice(c).price || 0) * c.quantity, 0);
    stats.textContent = `${cards.length} unique cards \u00B7 ${totalCards} total \u00B7 ${totalValue.toFixed(2)}\u20AC`;

    // Apply sorting
    const sortBy = document.getElementById("sort-select").value;
    const sorted = [...cards];
    switch (sortBy) {
        case "name-asc": sorted.sort((a, b) => a.name.localeCompare(b.name)); break;
        case "name-desc": sorted.sort((a, b) => b.name.localeCompare(a.name)); break;
        case "price-desc": sorted.sort((a, b) => (getDisplayPrice(b).price || 0) - (getDisplayPrice(a).price || 0)); break;
        case "price-asc": sorted.sort((a, b) => (getDisplayPrice(a).price || 0) - (getDisplayPrice(b).price || 0)); break;
        case "qty-desc": sorted.sort((a, b) => b.quantity - a.quantity); break;
        case "id-desc": sorted.sort((a, b) => b.id - a.id); break;
        case "id-asc": sorted.sort((a, b) => a.id - b.id); break;
    }

    const COND_TAG = {
        "Mint": ["MT", "#00bcd4"],
        "Near Mint": ["NM", "#4caf50"],
        "Excellent": ["EX", "#8bc34a"],
        "Good": ["GD", "#fdd835"],
        "Light Played": ["LP", "#ff9800"],
        "Played": ["PL", "#ff5722"],
        "Poor": ["PO", "#f44336"],
    };

    grid.innerHTML = sorted
        .map(
            (card) => {
                const { price: dp, dot } = getDisplayPrice(card);
                const price = dp ? `${Number(dp).toFixed(2)}\u20AC` : "";
                const ct = COND_TAG[card.condition];
                const condTag = ct ? `<span class="cond-tag" style="background:${ct[1]}">${ct[0]}</span>` : "";
                const dotClass = dot === "cm" ? "price-dot-cm" : dot === "fallback" ? "price-dot-fallback" : "";
                const dotTitle = dot === "cm" ? "Cardmarket price" : dot === "fallback" ? "Fallback price (selected source unavailable)" : "Automatic price";
                return `
        <div class="card-item" data-id="${card.id}">
            <div class="card-img-wrapper">
                <img src="${card.image_url || ""}" alt="${card.name}" loading="lazy">
                ${card.quantity > 1 ? `<span class="card-overlay-qty">x${card.quantity}</span>` : ""}
                ${dp && !card.price_manual ? `<span class="price-auto-dot ${dotClass}" title="${dotTitle}"></span>` : ""}
            </div>
            <div class="card-info">
                <div class="card-name" title="${card.name}">${card.name}</div>
                ${card.set_code ? `<div class="card-meta">${card.set_code}</div>` : ""}
                <div class="card-meta">${card.rarity}</div>
                <div class="card-bottom-row">
                    ${condTag}
                    <span class="card-bottom-lang">${langFlag(card.lang)}</span>
                    ${price ? `<span class="card-price">${price}</span>` : ""}
                </div>
            </div>
        </div>`;
            }
        )
        .join("");

    grid.querySelectorAll(".card-item").forEach((el) => {
        el.addEventListener("click", () => openCardModal(Number(el.dataset.id), cards));
    });
}

// --- Card Detail Modal ---
let currentModalCard = null;

async function openCardModal(id, cards) {
    let card = cards.find((c) => c.id === id);
    if (!card) return;

    currentModalCardId = id;
    currentModalCard = card;
    const modal = document.getElementById("card-modal");
    document.getElementById("modal-img").src = card.image_url || "";
    modal.hidden = false;

    const cmSearchUrl = buildCardmarketUrl(card.name, null, card.rarity, card.lang, card.set_code);

    document.getElementById("modal-details").innerHTML = `
        <p><strong>${card.name}</strong></p>
        <p>${card.type} ${card.race ? "/ " + card.race : ""}</p>
        ${card.atk != null ? `<p>ATK: ${card.atk} / DEF: ${card.def_ ?? "?"}</p>` : ""}
        ${card.archetype ? `<p>Archetype: ${card.archetype}</p>` : ""}
        <div class="price-section">
            <div class="price-input-row">
                <label>Trend \u20AC</label>
                <input type="number" id="modal-edit-price" step="0.01" min="0"
                       value="${card.price_cardmarket != null ? Number(card.price_cardmarket).toFixed(2) : ""}"
                       placeholder="0.00">
                <button type="button" id="modal-cm-price" class="btn-icon" title="Update prices from Cardmarket">CM</button>
            </div>
            <div class="price-cm-details">
                <span title="Minimum">Min: <strong id="modal-cm-min">${card.price_cm_min != null ? Number(card.price_cm_min).toFixed(2) + "\u20AC" : "—"}</strong></span>
                <span title="Average top 5">Avg: <strong id="modal-cm-avg">${card.price_cm_avg != null ? Number(card.price_cm_avg).toFixed(2) + "\u20AC" : "—"}</strong></span>
                <span title="Median top 5">Med: <strong id="modal-cm-median">${card.price_cm_median != null ? Number(card.price_cm_median).toFixed(2) + "\u20AC" : "—"}</strong></span>
            </div>
            <a href="${cmSearchUrl}" target="_blank" rel="noopener" id="modal-cardmarket-link" class="cardmarket-link">View on Cardmarket \u2197</a>
        </div>
    `;

    const rarityOpts = ["Common","Short Print","Rare","Super Rare","Ultra Rare","Secret Rare","Ultimate Rare","Ghost Rare","Gold Rare","Gold Secret Rare","Ghost/Gold Rare","Premium Gold Rare","Collector's Rare","Prismatic Secret Rare","Starlight Rare","Quarter Century Secret Rare","Platinum Secret Rare","Extra Secret Rare","Mosaic Rare","Shatterfoil Rare","Starfoil Rare","Duel Terminal Normal Parallel Rare","Duel Terminal Rare Parallel Rare","Duel Terminal Super Parallel Rare","Duel Terminal Ultra Parallel Rare","Super Parallel Rare","Ultra Rare (Pharaoh's Rare)"];
    const condOpts = ["Mint","Near Mint","Excellent","Good","Light Played","Played","Poor"];
    const langOpts = [["IT","Italian"],["EN","English"],["FR","French"],["DE","German"],["ES","Spanish"],["PT","Portuguese"],["JA","Japanese"],["KO","Korean"]];

    const infoEl = document.getElementById("modal-collection-info");
    infoEl.innerHTML = `
        <div class="form-row">
            <div class="form-group" style="flex:2">
                <label>Rarity</label>
                <select id="modal-edit-rarity">
                    ${rarityOpts.map((r) => `<option value="${r}" ${r === card.rarity ? "selected" : ""}>${r}</option>`).join("")}
                    ${!rarityOpts.includes(card.rarity) ? `<option value="${card.rarity}" selected>${card.rarity}</option>` : ""}
                </select>
            </div>
            <div class="form-group" style="flex:1">
                <label>Set Code</label>
                <select id="modal-select-set-code">
                    <option value="">Loading...</option>
                </select>
                <input type="text" id="modal-edit-set-code" value="${card.set_code || ""}" placeholder="e.g. BLMR-IT065" hidden>
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Condition</label>
                <select id="modal-edit-condition">
                    ${condOpts.map((c) => `<option value="${c}" ${c === card.condition ? "selected" : ""}>${c}</option>`).join("")}
                </select>
            </div>
            <div class="form-group">
                <label>Language ${langFlag(card.lang)}</label>
                <select id="modal-edit-lang">
                    ${langOpts.map(([v, l]) => `<option value="${v}" ${v === card.lang ? "selected" : ""}>${l}</option>`).join("")}
                </select>
            </div>
        </div>
        <div class="form-group">
            <label>Location</label>
            <input type="text" id="modal-edit-location" value="${(card.location || []).join(", ")}" placeholder="e.g. binder, deck blue-eyes...">
        </div>
    `;

    // Populate set code dropdown from YGOProDeck
    const setSelect = infoEl.querySelector("#modal-select-set-code");
    const setInput = infoEl.querySelector("#modal-edit-set-code");
    (async () => {
        try {
            const resp = await fetch(`https://db.ygoprodeck.com/api/v7/cardinfo.php?id=${card.card_id}`);
            if (resp.ok) {
                const apiSets = (await resp.json()).data?.[0]?.card_sets || [];
                setSelect.innerHTML = "";
                // Current value option (even if not in API)
                if (card.set_code && !apiSets.some((s) => s.set_code === card.set_code)) {
                    const opt = document.createElement("option");
                    opt.value = card.set_code;
                    opt.textContent = card.set_code + " (current)";
                    opt.selected = true;
                    setSelect.appendChild(opt);
                }
                apiSets.forEach((s) => {
                    const opt = document.createElement("option");
                    opt.value = s.set_code;
                    opt.textContent = `${s.set_code} (${s.set_rarity})`;
                    if (s.set_code === card.set_code) opt.selected = true;
                    setSelect.appendChild(opt);
                });
                // "Altro" option for manual input
                const otherOpt = document.createElement("option");
                otherOpt.value = "__other__";
                otherOpt.textContent = "Other...";
                setSelect.appendChild(otherOpt);
                // No set code yet
                if (!card.set_code) {
                    const emptyOpt = document.createElement("option");
                    emptyOpt.value = "";
                    emptyOpt.textContent = "— Select —";
                    emptyOpt.selected = true;
                    setSelect.prepend(emptyOpt);
                }
                // Update Cardmarket link with precise set name
                const matchedSet = apiSets.find(s => s.set_code === card.set_code);
                if (matchedSet) {
                    const cmLink = document.getElementById("modal-cardmarket-link");
                    if (cmLink) cmLink.href = buildCardmarketUrl(card.name, matchedSet.set_name, card.rarity, card.lang, card.set_code);
                }
            } else {
                // API failed — fallback to manual input
                setSelect.hidden = true;
                setInput.hidden = false;
            }
        } catch (e) {
            setSelect.hidden = true;
            setInput.hidden = false;
        }
    })();

    // Auto-save on change
    pendingModalSaves = [];
    const saveField = async (field, value) => {
        try {
            const resp = await fetch(`${API}/api/cards/${id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ [field]: value }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                alert(err.detail || "Error saving");
                return;
            }
            const updated = await resp.json();
            // If a merge happened, the returned card has a different id —
            // close the modal and refresh since this card no longer exists.
            if (updated.id !== id) {
                document.getElementById("card-modal").hidden = true;
                loadCollection();
            }
        } catch (e) { console.error(e); }
    };

    // Set code: switch between select and manual input
    setSelect.addEventListener("change", () => {
        if (setSelect.value === "__other__") {
            setSelect.hidden = true;
            setInput.hidden = false;
            setInput.value = "";
            setInput.focus();
        } else {
            pendingModalSaves.push(saveField("set_code", setSelect.value || null));
        }
    });
    setInput.addEventListener("change", () => {
        pendingModalSaves.push(saveField("set_code", setInput.value.trim() || null));
    });
    infoEl.querySelector("#modal-edit-rarity").addEventListener("change", (e) => {
        pendingModalSaves.push(saveField("rarity", e.target.value));
    });
    infoEl.querySelector("#modal-edit-condition").addEventListener("change", (e) => {
        pendingModalSaves.push(saveField("condition", e.target.value));
    });
    infoEl.querySelector("#modal-edit-lang").addEventListener("change", (e) => {
        pendingModalSaves.push(saveField("lang", e.target.value));
    });
    infoEl.querySelector("#modal-edit-location").addEventListener("change", (e) => {
        const loc = e.target.value.trim() ? e.target.value.split(",").map((s) => s.trim()).filter(Boolean) : null;
        pendingModalSaves.push(saveField("location", loc));
    });

    // Price: manual edit (save on blur/enter)
    // Price: manual edit — save price + mark as manual
    const priceInput = document.getElementById("modal-edit-price");
    priceInput.addEventListener("change", async () => {
        const val = priceInput.value.trim() === "" ? null : parseFloat(priceInput.value);
        const resp = await fetch(`${API}/api/cards/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ price_cardmarket: val, price_manual: true }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            alert(err.detail || "Error saving");
        }
    });

    // Price: refresh from API — resets price_manual to false
    document.getElementById("modal-cm-price").addEventListener("click", async () => {
        const btn = document.getElementById("modal-cm-price");
        btn.disabled = true;
        btn.textContent = "...";
        try {
            const resp = await fetch(`${API}/api/cards/${id}/cm-price`, { method: "POST" });
            const result = await resp.json();
            if (result.error === "extension_not_connected") {
                showToast("Firefox extension not connected", "error");
            } else if (result.error) {
                showToast(`Error: ${result.error}`, "error");
            } else {
                if (result.trend != null) {
                    priceInput.value = Number(result.trend).toFixed(2);
                    currentModalCard.price_cardmarket = result.trend;
                }
                const updates = { cm_min: "modal-cm-min", cm_avg: "modal-cm-avg", cm_median: "modal-cm-median" };
                for (const [key, elId] of Object.entries(updates)) {
                    if (result[key] != null) {
                        document.getElementById(elId).textContent = Number(result[key]).toFixed(2) + "\u20AC";
                        currentModalCard["price_" + key] = result[key];
                    }
                }
                const parts = [];
                if (result.trend != null) parts.push(`Trend: ${result.trend.toFixed(2)}\u20AC`);
                if (result.cm_min != null) parts.push(`Min: ${result.cm_min.toFixed(2)}\u20AC`);
                if (result.cm_avg != null) parts.push(`Avg: ${result.cm_avg.toFixed(2)}\u20AC`);
                if (result.cm_median != null) parts.push(`Med: ${result.cm_median.toFixed(2)}\u20AC`);
                showToast(parts.join(" · ") || "No price found");
            }
        } catch (e) { console.error(e); showToast("Connection error", "error"); }
        btn.disabled = false;
        btn.textContent = "CM";
    });

    document.getElementById("modal-quantity").textContent = `x${card.quantity}`;
    // Show split button only if quantity > 1
    document.getElementById("modal-split").style.display = card.quantity > 1 ? "" : "none";
}

document.getElementById("modal-increase").addEventListener("click", async () => {
    const qty = await updateQuantity(1);
    if (qty !== null) {
        document.getElementById("modal-quantity").textContent = `x${qty}`;
        showToast(`Quantity updated: x${qty}`);
    }
});

document.getElementById("modal-decrease").addEventListener("click", async () => {
    const qty = await updateQuantity(-1);
    if (qty !== null) {
        document.getElementById("modal-quantity").textContent = `x${qty}`;
        showToast(`Quantity updated: x${qty}`);
    }
});

async function updateQuantity(delta) {
    const qtyEl = document.getElementById("modal-quantity");
    const current = parseInt(qtyEl.textContent.replace("x", ""));
    const newQty = Math.max(1, current + delta);
    try {
        const resp = await fetch(`${API}/api/cards/${currentModalCardId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ quantity: newQty }),
        });
        if (resp.ok) return newQty;
    } catch (e) {
        console.error(e);
    }
    return null;
}

document.getElementById("modal-delete").addEventListener("click", async () => {
    if (!confirm("Remove this card from the collection?")) return;
    try {
        await fetch(`${API}/api/cards/${currentModalCardId}`, { method: "DELETE" });
        document.getElementById("card-modal").hidden = true;
        loadCollection();
    } catch (e) {
        console.error(e);
    }
});

// --- Split ---
document.getElementById("modal-split").addEventListener("click", () => {
    if (!currentModalCard) return;
    const card = currentModalCard;

    document.getElementById("split-info").textContent =
        `${card.name} — currently x${card.quantity} (${card.rarity}, ${card.condition}) ${langFlag(card.lang)}`;
    document.getElementById("split-qty").value = 1;
    document.getElementById("split-qty").max = card.quantity - 1;

    // Copy rarity options from add-rarity and pre-select current
    const splitRarity = document.getElementById("split-rarity");
    splitRarity.innerHTML = document.getElementById("add-rarity").innerHTML;
    splitRarity.value = card.rarity;

    document.getElementById("split-condition").value = card.condition;
    document.getElementById("split-lang").value = card.lang;

    document.getElementById("split-modal").hidden = false;
});

document.getElementById("split-confirm").addEventListener("click", async () => {
    if (!currentModalCardId) return;

    const qty = parseInt(document.getElementById("split-qty").value) || 1;
    const rarity = document.getElementById("split-rarity").value;
    const condition = document.getElementById("split-condition").value;
    const lang = document.getElementById("split-lang").value;

    try {
        const resp = await fetch(`${API}/api/cards/${currentModalCardId}/split`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ quantity: qty, rarity, condition, lang }),
        });
        if (resp.ok) {
            showToast("Card split!");
            document.getElementById("split-modal").hidden = true;
            document.getElementById("card-modal").hidden = true;
            loadCollection();
        } else {
            const err = await resp.json();
            alert(err.detail || "Error");
        }
    } catch (e) {
        console.error(e);
    }
});

// Close modals
document.querySelectorAll(".modal-close").forEach((btn) => {
    btn.addEventListener("click", async () => {
        const modal = btn.closest(".modal");
        modal.hidden = true;
        if (modal.id === "card-modal") {
            await Promise.all(pendingModalSaves);
            pendingModalSaves = [];
            loadCollection();
        }
    });
});

document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", async () => {
        const modal = backdrop.closest(".modal");
        modal.hidden = true;
        if (modal.id === "card-modal") {
            await Promise.all(pendingModalSaves);
            pendingModalSaves = [];
            loadCollection();
        }
    });
});

// =============================================
// --- Scanner (live camera) ---
// =============================================
let currentStream = null;
let previewInterval = null;
let previewBusy = false;
let autoScanName = "";       // name of stable match
let autoScanCount = 0;       // consecutive frames with same match
let autoScanTriggered = false; // prevent re-triggering
const AUTO_SCAN_THRESHOLD = 0.60;  // minimum confidence
const AUTO_SCAN_FRAMES = 4;        // consecutive stable frames needed

// Smooth detection state: prevent flickering
let lastDetectedMode = "no_card";
let lastDetectedName = "";
let lastDetectedConf = 0;
let noCardFrames = 0;
const NO_CARD_GRACE = 3; // frames of "no_card" before we actually show it

function switchToView(viewId) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.getElementById(`view-${viewId}`).classList.add("active");
    // Update nav buttons (only for main tabs)
    document.querySelectorAll(".nav-btn").forEach((b) => {
        b.classList.toggle("active", b.dataset.view === viewId);
    });
}

function resetScanner() {
    document.getElementById("camera-container").style.display = "block";
    document.getElementById("capture-btn").hidden = false;
    document.getElementById("ocr-live-preview").hidden = false;
    document.getElementById("scan-loading").hidden = true;
    autoScanName = "";
    autoScanCount = 0;
    autoScanTriggered = false;
    noCardFrames = 0;
    lastDetectedMode = "no_card";
    lastDetectedName = "";
    lastDetectedConf = 0;
    // Reset text content only, never touch structure
    document.getElementById("pv-detect-text").textContent = "Starting camera...";
    document.getElementById("pv-detect-dot").style.background = "";
    document.getElementById("pv-match-text").textContent = "";
    document.getElementById("pv-match-conf").textContent = "";
    document.getElementById("pv-match-dot").style.background = "transparent";
    document.getElementById("pv-auto-info").textContent = "";
    startCamera();
}

async function startCamera() {
    if (currentStream) return;
    try {
        currentStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } },
        });
        const video = document.getElementById("camera-feed");
        video.srcObject = currentStream;

        video.addEventListener("loadedmetadata", () => {
            const isPortrait = window.innerHeight > window.innerWidth;
            const videoLandscape = video.videoWidth > video.videoHeight;
            const container = document.getElementById("camera-container");

            if (isPortrait && videoLandscape) {
                video.classList.add("video-rotate-fix");
                const scale = container.clientWidth / video.videoHeight;
                container.style.height = Math.round(video.videoWidth * scale) + "px";
            } else {
                video.classList.remove("video-rotate-fix");
                container.style.height = "";
            }
        }, { once: true });

        startPreviewLoop();
    } catch (e) {
        console.error("Camera error:", e);
        alert("Unable to access the camera. Please check permissions.");
    }
}

function stopCamera() {
    stopPreviewLoop();
    if (currentStream) {
        currentStream.getTracks().forEach((t) => t.stop());
        currentStream = null;
    }
}

function startPreviewLoop() {
    stopPreviewLoop();
    previewBusy = false;
    document.getElementById("ocr-live-preview").hidden = false;

    previewInterval = setInterval(() => {
        if (previewBusy) return;
        previewBusy = true;
        sendPreviewFrame().finally(() => { previewBusy = false; });
    }, 200);
}

function stopPreviewLoop() {
    if (previewInterval) {
        clearInterval(previewInterval);
        previewInterval = null;
    }
}

function getRotation() {
    const active = document.querySelector(".rot-btn.active");
    return active ? parseInt(active.dataset.rot) : 0;
}

document.querySelectorAll(".rot-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".rot-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        // Reset auto-scan so it re-evaluates with new rotation
        autoScanName = "";
        autoScanCount = 0;
        autoScanTriggered = false;
    });
});

async function sendPreviewFrame() {
    const video = document.getElementById("camera-feed");
    if (!video || video.videoWidth === 0) return;

    const c = document.createElement("canvas");
    c.width = video.videoWidth;
    c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0);

    const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.85));
    if (!blob) return;

    const form = new FormData();
    form.append("file", blob, "preview.jpg");
    form.append("rotation", getRotation());

    try {
        const resp = await fetch(`${API}/api/ocr-preview`, { method: "POST", body: form });
        if (!resp.ok) return;
        const data = await resp.json();
        renderPreview(data);
    } catch (e) { /* ignore */ }
}

function renderPreview(data) {
    const container = document.getElementById("ocr-live-preview");

    // Smooth out flickering: don't show "no_card" until N consecutive frames
    if (data.mode === "no_card" || data.mode === "no_image") {
        noCardFrames++;
        autoScanName = "";
        autoScanCount = 0;
        if (noCardFrames < NO_CARD_GRACE && lastDetectedMode === "detected") {
            return; // keep showing last detection
        }
        lastDetectedMode = "no_card";
        _updatePreviewStatus(container, null, 0);
        _updatePreviewDebug(container, data);
        return;
    }

    // mode === "detected"
    noCardFrames = 0;
    lastDetectedMode = "detected";

    const hasHash = data.hash_match_name && data.hash_match_name.length > 0;
    const conf = data.hash_match_confidence || 0;

    if (hasHash) {
        lastDetectedName = data.hash_match_name;
        lastDetectedConf = conf;
    }

    // Auto-scan: if same card detected stably at high confidence, trigger scan
    if (hasHash && conf >= AUTO_SCAN_THRESHOLD && !autoScanTriggered) {
        if (data.hash_match_name === autoScanName) {
            autoScanCount++;
        } else {
            autoScanName = data.hash_match_name;
            autoScanCount = 1;
        }
        if (autoScanCount >= AUTO_SCAN_FRAMES) {
            autoScanTriggered = true;
            document.getElementById("capture-btn").click();
            return;
        }
    } else if (!hasHash || conf < AUTO_SCAN_THRESHOLD) {
        autoScanName = "";
        autoScanCount = 0;
    }

    _updatePreviewStatus(container, hasHash ? data.hash_match_name : null, conf);
    _updatePreviewDebug(container, data);
}

function _updatePreviewStatus(container, matchName, conf) {

    const detectDot = container.querySelector("#pv-detect-dot");
    const detectText = container.querySelector("#pv-detect-text");
    const matchDot = container.querySelector("#pv-match-dot");
    const matchText = container.querySelector("#pv-match-text");
    const matchConf = container.querySelector("#pv-match-conf");
    const autoInfoEl = container.querySelector("#pv-auto-info");

    if (!matchName && lastDetectedMode === "no_card") {
        detectDot.style.background = "var(--red)";
        detectText.textContent = "No card detected";
        matchDot.style.background = "transparent";
        matchText.textContent = "";
        matchConf.textContent = "";
        autoInfoEl.textContent = "";
        return;
    }

    detectDot.style.background = "var(--green)";
    detectText.textContent = "Card detected";

    if (matchName) {
        const confColor = conf > 0.7 ? "var(--green)" : conf > 0.4 ? "var(--yellow)" : "var(--red)";
        matchDot.style.background = confColor;
        matchText.textContent = matchName;
        matchConf.textContent = `${(conf * 100).toFixed(0)}%`;
        matchConf.style.color = confColor;
        autoInfoEl.textContent = conf >= AUTO_SCAN_THRESHOLD && autoScanCount > 0
            ? `Auto ${autoScanCount}/${AUTO_SCAN_FRAMES}` : "";
    } else {
        matchDot.style.background = "var(--yellow)";
        matchText.textContent = "No match";
        matchConf.textContent = "";
        autoInfoEl.textContent = "";
    }
}

function _updatePreviewDebug(container, data) {
    // Only update debug images if the details panel is actually open
    const details = container.querySelector("#preview-debug");
    if (!details || !details.open) return;

    // Update src on fixed <img> elements — no DOM creation/destruction
    const artwork = document.getElementById("pv-dbg-artwork");
    const warped = document.getElementById("pv-dbg-warped");
    const detect = document.getElementById("pv-dbg-detect");

    if (data.artwork_debug) {
        artwork.src = "data:image/jpeg;base64," + data.artwork_debug;
        artwork.hidden = false;
    }
    if (data.warped_image) {
        warped.src = "data:image/jpeg;base64," + data.warped_image;
        warped.hidden = false;
    }
    if (data.debug_image) {
        detect.src = "data:image/jpeg;base64," + data.debug_image;
        detect.hidden = false;
    }

    // Set code debug
    const scDiv = document.getElementById("pv-dbg-setcode");
    if (data.set_code_img) {
        document.getElementById("pv-dbg-setcode-img").src = "data:image/jpeg;base64," + data.set_code_img;
        if (data.set_code_processed) {
            document.getElementById("pv-dbg-setcode-proc").src = "data:image/jpeg;base64," + data.set_code_processed;
        }
        const ocrText = data.set_code_ocr || data.set_code_raw || "(no text)";
        document.getElementById("pv-dbg-setcode-text").textContent = `OCR: ${ocrText}`;
        scDiv.hidden = false;
    }
}

// Capture button
document.getElementById("capture-btn").addEventListener("click", async () => {
    stopPreviewLoop();

    const video = document.getElementById("camera-feed");
    const canvas = document.getElementById("capture-canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);

    document.getElementById("camera-container").style.display = "none";
    document.getElementById("capture-btn").hidden = true;
    document.getElementById("ocr-live-preview").hidden = true;
    document.getElementById("scan-loading").hidden = false;

    canvas.toBlob(async (blob) => {
        const form = new FormData();
        form.append("file", blob, "scan.jpg");
        form.append("rotation", getRotation());

        try {
            const resp = await fetch(`${API}/api/scan`, { method: "POST", body: form });
            const data = await resp.json();
            document.getElementById("scan-loading").hidden = true;

            if (!resp.ok) {
                alert(data.detail || "Error during scan");
                resetScanner();
                return;
            }
            showScanResults(data);
        } catch (e) {
            console.error(e);
            document.getElementById("scan-loading").hidden = true;
            alert("Server connection error");
            resetScanner();
        }
    }, "image/png");
});

function renderSetsList(sets) {
    if (!sets || sets.length === 0) return "";
    return `<div class="card-sets-list">
        ${sets.map((s) => {
            return `<div class="card-set-item">
                <span class="set-code">${s.set_code}</span>
                <span class="set-name">${s.set_name}</span>
                <span class="set-rarity">${s.set_rarity}</span>
                ${s.set_price ? `<span class="set-price">${s.set_price}&euro;</span>` : ""}
            </div>`;
        }).join("")}
    </div>`;
}

function showScanResults(data) {
    stopCamera();

    // Fast path: single high-confidence match → skip results, go directly to add modal
    if (data.candidates.length === 1 && data.extracted_text.includes("Image Match")) {
        const card = data.candidates[0];
        const cardForAdd = { ...card };
        const sets = card.sets || [];
        delete cardForAdd.sets;
        openAddModal(cardForAdd, sets);
        return;
    }

    document.getElementById("ocr-text").textContent = data.extracted_text;
    switchToView("results");

    const grid = document.getElementById("results-grid");
    if (data.candidates.length === 0) {
        grid.innerHTML = "<p>No results found. Try again with a better photo.</p>";
    } else {
        grid.innerHTML = data.candidates
            .map(
                (card) => {
                    const cardForAdd = { ...card };
                    const setsJson = JSON.stringify(card.sets || []).replace(/'/g, "&#39;");
                    delete cardForAdd.sets;

                    return `
            <div class="card-item scan-result-card">
                <img src="${card.image_url || ""}" alt="${card.name}" loading="lazy">
                <div class="card-info">
                    <div class="card-name" title="${card.name}">${card.name}</div>
                    <div class="card-meta">${card.type}</div>
                    <button class="btn-add" data-card='${JSON.stringify(cardForAdd).replace(/'/g, "&#39;")}' data-sets='${setsJson}'>
                        Add
                    </button>
                    ${card.sets && card.sets.length > 0
                        ? `<details class="sets-details"><summary>${card.sets.length} expansions</summary>${renderSetsList(card.sets)}</details>`
                        : ""}
                </div>
            </div>`;
                }
            )
            .join("");

        grid.querySelectorAll(".btn-add").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const cardData = JSON.parse(btn.dataset.card);
                const sets = JSON.parse(btn.dataset.sets || "[]");
                openAddModal(cardData, sets);
            });
        });
    }
}

document.getElementById("back-to-camera").addEventListener("click", () => {
    switchToView("scanner");
    resetScanner();
});

// --- Add card to collection ---
let pendingCardData = null;
let pendingCardSets = null;

function detectLangFromSetCode(setCode) {
    if (!setCode) return null;
    const match = setCode.match(/-([A-Z]{2})\d/);
    if (match) {
        const lang = match[1];
        const valid = ["IT", "EN", "FR", "DE", "ES", "PT", "JA", "KO"];
        if (valid.includes(lang)) return lang;
    }
    return null;
}

function openAddModal(cardData, sets) {
    // Close any other open modals first
    document.querySelectorAll(".modal").forEach((m) => { m.hidden = true; });
    pendingCardData = cardData;
    pendingCardSets = sets;

    document.getElementById("add-modal-img").src = cardData.image_url || "";
    document.getElementById("add-modal-name").textContent = cardData.name;
    document.getElementById("add-modal-type").textContent = cardData.type;

    // Populate sets dropdown
    const select = document.getElementById("add-set-select");
    select.innerHTML = "";
    if (sets && sets.length > 0) {
        sets.forEach((s) => {
            const opt = document.createElement("option");
            opt.value = JSON.stringify({ set_code: s.set_code, set_rarity: s.set_rarity, set_name: s.set_name, set_price: s.set_price || null });
            const priceStr = s.set_price ? ` — ${s.set_price}\u20AC` : "";
            opt.textContent = `${s.set_code} — ${s.set_name} (${s.set_rarity})${priceStr}`;
            select.appendChild(opt);
        });
    } else {
        const opt = document.createElement("option");
        opt.value = JSON.stringify({ set_code: "N/A", set_rarity: "Common", set_name: "Unknown" });
        opt.textContent = "No expansion found";
        select.appendChild(opt);
    }

    // Sync rarity dropdown when set changes
    const raritySelect = document.getElementById("add-rarity");
    function syncRarity() {
        try {
            const setData = JSON.parse(select.value);
            const rarity = setData.set_rarity || "Common";
            // If the rarity exists in the dropdown, select it; otherwise add it
            const existing = [...raritySelect.options].find((o) => o.value === rarity);
            if (existing) {
                raritySelect.value = rarity;
            } else {
                const opt = document.createElement("option");
                opt.value = rarity;
                opt.textContent = rarity;
                raritySelect.appendChild(opt);
                raritySelect.value = rarity;
            }
        } catch (e) { /* ignore */ }
    }
    select.addEventListener("change", syncRarity);
    syncRarity(); // set initial value

    // Language: auto-detect from set code, fallback to last used, then IT
    const detectedSetCode = sets?.length ? sets[0].set_code : "";
    const detectedLang = detectLangFromSetCode(detectedSetCode);
    const lastLang = localStorage.getItem("yugipy_last_lang") || "IT";
    document.getElementById("add-lang").value = detectedLang || lastLang;

    // Condition: restore last used
    const lastCondition = localStorage.getItem("yugipy_last_condition") || "Near Mint";
    document.getElementById("add-condition").value = lastCondition;

    document.getElementById("add-qty").value = 1;
    document.getElementById("add-location").value = "";

    document.getElementById("add-modal").hidden = false;
}

document.getElementById("add-modal-confirm").addEventListener("click", async () => {
    if (!pendingCardData) return;

    const rarity = document.getElementById("add-rarity").value;
    const condition = document.getElementById("add-condition").value;
    const lang = document.getElementById("add-lang").value;
    const locationRaw = document.getElementById("add-location").value.trim();
    const location = locationRaw ? locationRaw.split(",").map((s) => s.trim()).filter(Boolean) : null;

    // Use set-specific price if available, otherwise keep the generic one
    const setData = JSON.parse(document.getElementById("add-set-select").value);
    const cardDataWithPrice = { ...pendingCardData };
    if (setData.set_price && setData.set_price > 0) {
        cardDataWithPrice.price_cardmarket = setData.set_price;
    }

    const payload = {
        ...cardDataWithPrice,
        set_code: (setData.set_code && setData.set_code !== "N/A") ? setData.set_code : null,
        rarity,
        condition,
        lang,
        location,
        quantity: parseInt(document.getElementById("add-qty").value) || 1,
    };

    try {
        const resp = await fetch(`${API}/api/cards`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (resp.ok) {
            // Remember preferences for next time
            localStorage.setItem("yugipy_last_lang", lang);
            localStorage.setItem("yugipy_last_condition", condition);

            showToast("Card added to collection!");
            document.getElementById("add-modal").hidden = true;
            loadCollection();
            // If we came from scanner, go back to scan next card
            if (document.getElementById("view-scanner").classList.contains("active")
                || !document.querySelector(".view.active")) {
                switchToView("scanner");
                resetScanner();
            }
        } else {
            const err = await resp.json();
            alert(err.detail || "Error adding card");
        }
    } catch (e) {
        console.error(e);
    }
});

// --- Collection local filter ---
document.getElementById("search-input").addEventListener("input", applyLocalFilters);

// --- Add new card (manual search on YGOProDeck) ---
document.getElementById("add-new-btn").addEventListener("click", () => {
    const modal = document.getElementById("search-modal");
    document.getElementById("search-results-grid").innerHTML = '<p class="text-muted">Search for a card by name to add it to the collection.</p>';
    document.getElementById("ygopro-search-input").value = "";
    modal.hidden = false;
    setTimeout(() => document.getElementById("ygopro-search-input").focus(), 100);
});

let searchTimeout = null;
document.getElementById("ygopro-search-input").addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(doSearch, 400);
});

async function doSearch() {
    const q = document.getElementById("ygopro-search-input").value.trim();
    if (q.length < 2) {
        document.getElementById("search-results-grid").innerHTML = '<p class="text-muted">Search for a card by name to add it to the collection.</p>';
        return;
    }

    try {
        const resp = await fetch(`${API}/api/search?q=${encodeURIComponent(q)}`);
        const results = await resp.json();

        const modal = document.getElementById("search-modal");
        const grid = document.getElementById("search-results-grid");

        if (results.length === 0) {
            grid.innerHTML = "<p>No results for this search.</p>";
        } else {
            grid.innerHTML = results
                .map((card) => {
                    const cardForAdd = { ...card };
                    const setsJson = JSON.stringify(card.sets || []).replace(/'/g, "&#39;");
                    delete cardForAdd.sets;
                    return `
                <div class="card-item">
                    <img src="${card.image_url || ""}" alt="${card.name}" loading="lazy">
                    <div class="card-info">
                        <div class="card-name" title="${card.name}">${card.name}</div>
                        <div class="card-meta">${card.type}</div>
                        <button class="btn-add" data-card='${JSON.stringify(cardForAdd).replace(/'/g, "&#39;")}' data-sets='${setsJson}'>
                            Add
                        </button>
                    </div>
                </div>`;
                })
                .join("");

            grid.querySelectorAll(".btn-add").forEach((btn) => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    const cardData = JSON.parse(btn.dataset.card);
                    const sets = JSON.parse(btn.dataset.sets || "[]");
                    openAddModal(cardData, sets);
                });
            });
        }
    } catch (e) {
        console.error(e);
    }
}

async function fetchSetsAndOpenModal(cardData) {
    try {
        const resp = await fetch(`https://db.ygoprodeck.com/api/v7/cardinfo.php?id=${cardData.card_id}`);
        if (resp.ok) {
            const data = await resp.json();
            const cardSets = (data.data?.[0]?.card_sets || []).map((s) => ({
                set_code: s.set_code || "",
                set_name: s.set_name || "",
                set_rarity: s.set_rarity || "",
                set_price: s.set_price ? parseFloat(s.set_price) : null,
            }));
            openAddModal(cardData, cardSets, null);
        } else {
            openAddModal(cardData, [], null);
        }
    } catch (e) {
        openAddModal(cardData, [], null);
    }
}

// --- Toast ---
function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2200);
}

// --- Price Display Setting ---
const priceSelect = document.getElementById("setting-price-display");
priceSelect.value = priceDisplayMode;
priceSelect.addEventListener("change", () => {
    priceDisplayMode = priceSelect.value;
    saveSetting("priceDisplay", priceDisplayMode);
    renderCollection(window._lastCards || []);
});

// --- Setup Wizard ---
(async function initSetupWizard() {
    const statusInfo = document.getElementById("setup-status-info");
    const wizard = document.getElementById("setup-wizard");
    const badge = document.getElementById("setup-status-badge");
    const runBtn = document.getElementById("setup-run-btn");
    const updateBtn = document.getElementById("setup-update-btn");
    const cancelBtn = document.getElementById("setup-cancel-btn");
    const bar = document.getElementById("setup-bar");
    const progressText = document.getElementById("setup-progress-text");

    async function loadStatus() {
        try {
            const resp = await fetch(`${API}/api/setup/status`);
            const s = await resp.json();

            if (s.running) {
                statusInfo.innerHTML = `<p class="text-muted">Setup in progress...</p>`;
                badge.hidden = true;
                runBtn.hidden = true;
                updateBtn.hidden = true;
                return;
            }

            if (s.ready) {
                badge.hidden = false;
                badge.className = "badge badge-ok";
                badge.textContent = "Ready";
                statusInfo.innerHTML = `<p class="text-muted">${s.hash_count.toLocaleString()} cards indexed &middot; ${s.full_images.toLocaleString()} images &middot; ${(s.hash_db_size / 1024 / 1024).toFixed(1)} MB</p>`;
                runBtn.hidden = true;
                updateBtn.hidden = false;
            } else {
                badge.hidden = false;
                badge.className = "badge badge-warn";
                badge.textContent = "Not configured";
                statusInfo.innerHTML = `<p class="text-muted">The card recognition index has not been created yet. Start setup to download images and build the index.</p>`;
                runBtn.hidden = false;
                updateBtn.hidden = true;
            }
        } catch (e) {
            statusInfo.innerHTML = `<p class="text-muted">Error loading status.</p>`;
        }
    }

    function setStepState(stepNum, state) {
        const el = document.querySelector(`.setup-step[data-step="${stepNum}"]`);
        if (!el) return;
        el.className = "setup-step" + (state ? " " + state : "");
        const icon = el.querySelector(".step-icon");
        if (state === "done") icon.textContent = "●";
        else if (state === "active") icon.textContent = "◉";
        else icon.textContent = "○";
    }

    function resetSteps() {
        for (let i = 1; i <= 4; i++) setStepState(i, "");
    }

    async function runSetup() {
        wizard.hidden = false;
        runBtn.hidden = true;
        updateBtn.hidden = true;
        cancelBtn.hidden = false;
        badge.hidden = true;
        resetSteps();
        bar.style.width = "0%";
        bar.style.background = "#29b6f6";
        progressText.textContent = "";

        const evtSource = new EventSource(`${API}/api/setup/run`);
        let currentStep = 0;

        evtSource.onmessage = (e) => {
            const d = JSON.parse(e.data);

            if (d.error) {
                evtSource.close();
                progressText.textContent = d.error === "already_running"
                    ? "Setup already running in another session."
                    : `Error: ${d.message || d.error}`;
                bar.style.background = "#e53935";
                cancelBtn.hidden = true;
                runBtn.hidden = false;
                return;
            }

            if (d.type === "step") {
                if (currentStep > 0) setStepState(currentStep, "done");
                currentStep = d.step;
                setStepState(currentStep, "active");
                progressText.textContent = d.label;
            }

            if (d.type === "info") {
                progressText.textContent = d.message;
            }

            if (d.type === "progress") {
                if (d.total > 0) {
                    const pct = Math.round((d.done / d.total) * 100);
                    bar.style.width = `${pct}%`;
                    let text = `${d.done}/${d.total}`;
                    if (d.failed) text += ` (${d.failed} failed)`;
                    if (d.skipped) text += ` (${d.skipped} skipped)`;
                    progressText.textContent = d.message || text;
                } else if (d.message) {
                    progressText.textContent = d.message;
                }
            }

            if (d.type === "done") {
                evtSource.close();
                setStepState(currentStep, "done");
                bar.style.width = "100%";
                bar.style.background = "#4caf50";
                progressText.textContent = "Setup complete!";
                cancelBtn.hidden = true;
                showToast("Card index configured!");
                setTimeout(() => {
                    wizard.hidden = true;
                    loadStatus();
                }, 3000);
            }

            if (d.type === "cancelled") {
                evtSource.close();
                progressText.textContent = "Cancelled.";
                bar.style.background = "#ffa726";
                cancelBtn.hidden = true;
                loadStatus();
            }
        };

        evtSource.onerror = () => {
            evtSource.close();
            progressText.textContent = "Connection lost.";
            bar.style.background = "#e53935";
            cancelBtn.hidden = true;
            loadStatus();
        };
    }

    runBtn.addEventListener("click", runSetup);
    updateBtn.addEventListener("click", runSetup);

    cancelBtn.addEventListener("click", async () => {
        await fetch(`${API}/api/setup/cancel`, { method: "POST" });
        cancelBtn.disabled = true;
        cancelBtn.textContent = "Cancelling...";
        setTimeout(() => {
            cancelBtn.disabled = false;
            cancelBtn.textContent = "Cancel";
        }, 3000);
    });

    loadStatus();
})();



// --- Cardmarket Bulk Sync ---
let bulkPollTimer = null;

document.getElementById("cm-bulk-start").addEventListener("click", async () => {
    const resp = await fetch(`${API}/api/cm-bulk/start`, { method: "POST" });
    const data = await resp.json();
    if (data.error === "extension_not_connected") {
        showToast("Firefox extension not connected", "error");
        return;
    }
    if (data.error === "already_running") {
        showToast("Sync already running", "error");
        return;
    }
    document.getElementById("cm-bulk-start").hidden = true;
    document.getElementById("cm-bulk-stop").hidden = false;
    document.getElementById("cm-bulk-progress").hidden = false;
    document.getElementById("cm-bulk-failed").hidden = true;
    startBulkPoll();
});

document.getElementById("cm-bulk-stop").addEventListener("click", async () => {
    const btn = document.getElementById("cm-bulk-stop");
    btn.disabled = true;
    btn.textContent = "Stopping...";
    btn.style.background = "#ffa726";
    await fetch(`${API}/api/cm-bulk/stop`, { method: "POST" });
});

document.getElementById("cm-bulk-resume").addEventListener("click", async () => {
    await fetch(`${API}/api/cm-bulk/resume`, { method: "POST" });
    document.getElementById("cm-bulk-resume").hidden = true;
});

function startBulkPoll() {
    if (bulkPollTimer) clearInterval(bulkPollTimer);
    bulkPollTimer = setInterval(pollBulkStatus, 2000);
    pollBulkStatus();
}

async function pollBulkStatus() {
    try {
        const resp = await fetch(`${API}/api/cm-bulk/status`);
        const p = await resp.json();
        const pct = p.total > 0 ? Math.round((p.done / p.total) * 100) : 0;
        document.getElementById("cm-bulk-bar").style.width = `${pct}%`;

        let statusText = `${p.done}/${p.total} (${p.ok} ok, ${p.failed.length} failed)`;
        if (p.status === "cloudflare") {
            statusText += " \u2014 CLOUDFLARE: solve the captcha in the open tab, then click Resume";
            document.getElementById("cm-bulk-resume").hidden = false;
            document.getElementById("cm-bulk-bar").style.background = "#ffa726";
        } else if (p.status === "paused") {
            statusText += " \u2014 Paused";
            document.getElementById("cm-bulk-bar").style.background = "#ffa726";
        } else if (p.status === "running") {
            document.getElementById("cm-bulk-bar").style.background = "#29b6f6";
        }
        document.getElementById("cm-bulk-status").textContent = statusText;

        if (p.status === "done" || p.status === "cancelled" || p.status.startsWith("error")) {
            clearInterval(bulkPollTimer);
            bulkPollTimer = null;
            document.getElementById("cm-bulk-start").hidden = false;
            const stopBtn = document.getElementById("cm-bulk-stop");
            stopBtn.hidden = true;
            stopBtn.disabled = false;
            stopBtn.textContent = "Stop";
            stopBtn.style.background = "#e53935";
            document.getElementById("cm-bulk-resume").hidden = true;
            if (p.status === "done") {
                document.getElementById("cm-bulk-bar").style.background = "#4caf50";
                showToast(`Bulk sync complete: ${p.ok} updated, ${p.failed.length} failed`);
            } else {
                showToast(`Bulk sync ${p.status}`);
            }
            if (p.failed.length > 0) {
                document.getElementById("cm-bulk-failed").hidden = false;
                document.getElementById("cm-bulk-failed-list").innerHTML = p.failed
                    .map(f => `<li>${f.name} \u2014 ${f.error}</li>`).join("");
            }
            loadCollection();
        }
    } catch (e) { console.error(e); }
}

// =============================================
// --- Book ---
// =============================================

const RARITY_ORDER = {
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

const TYPE_GROUP = {
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

const TYPE_ORDER = {
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

let bookPages = [];
let bookCurrentSpread = 0;

function loadBook() {
    // Reuse allCollectionCards if already loaded, otherwise fetch
    if (allCollectionCards.length > 0) {
        buildAndRenderBook();
    } else {
        fetch(`${API}/api/cards`)
            .then((r) => r.json())
            .then((cards) => {
                allCollectionCards = cards;
                buildAndRenderBook();
            })
            .catch((e) => console.error("Failed to load book:", e));
    }
}

function buildAndRenderBook() {
    // Populate set filter dropdown
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

    // Filter cards
    let filtered = allCollectionCards.filter(card => {
        if (filterLang && card.lang !== filterLang) return false;
        if (minCondRank >= 0 && (CONDITION_RANK[card.condition] ?? 0) < minCondRank) return false;
        if (filterSet && !(card.set_code || "").startsWith(filterSet)) return false;
        if (minPrice > 0 && (getDisplayPrice(card).price || 0) < minPrice) return false;
        return true;
    });

    // Expand cards by quantity (each copy = one slot), respecting max copies
    const expanded = [];
    for (const card of filtered) {
        const copies = maxCopies > 0 ? Math.min(card.quantity, maxCopies) : card.quantity;
        for (let i = 0; i < copies; i++) {
            expanded.push(card);
        }
    }

    // Group
    const groups = new Map();
    for (const card of expanded) {
        let key;
        switch (groupBy) {
            case "set":
                key = card.set_code ? card.set_code.split("-")[0] : "Other";
                break;
            case "archetype":
                key = card.archetype || "No archetype";
                break;
            case "type":
                key = TYPE_GROUP[card.type] || card.type || "Other";
                break;
            default:
                key = "";
        }
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(card);
    }

    // Sort group keys
    const sortedKeys = [...groups.keys()].sort((a, b) => {
        if (a === "Other" || a === "No archetype") return 1;
        if (b === "Other" || b === "No archetype") return -1;
        // Use TYPE_ORDER if grouping by type
        if (groupBy === "type") {
            return (TYPE_ORDER[a] ?? 99) - (TYPE_ORDER[b] ?? 99);
        }
        return a.localeCompare(b);
    });

    // Sort cards within each group
    const sortFn = (a, b) => {
        switch (sortBy) {
            case "rarity":
                return (RARITY_ORDER[b.rarity] ?? -1) - (RARITY_ORDER[a.rarity] ?? -1);
            case "name":
                return a.name.localeCompare(b.name);
            case "set_code":
                return (a.set_code || "").localeCompare(b.set_code || "");
            case "price":
                return (getDisplayPrice(b).price || 0) - (getDisplayPrice(a).price || 0);
            default:
                return 0;
        }
    };

    // Build pages
    bookPages = [];

    if (groupBy === "none" || !newPagePerGroup) {
        // Flat layout: all cards sequentially
        const allCards = [];
        for (const key of sortedKeys) {
            groups.get(key).sort(sortFn);
            allCards.push(...groups.get(key));
        }
        for (let i = 0; i < allCards.length; i += slotsPerPage) {
            bookPages.push({ group: null, slots: allCards.slice(i, i + slotsPerPage) });
        }
    } else {
        // Grouped: each group starts on a new page
        for (const key of sortedKeys) {
            const cards = groups.get(key).sort(sortFn);
            for (let i = 0; i < cards.length; i += slotsPerPage) {
                bookPages.push({
                    group: key,
                    slots: cards.slice(i, i + slotsPerPage),
                });
            }
            // Pad last page of group with nulls
            const lastPage = bookPages[bookPages.length - 1];
            while (lastPage.slots.length < slotsPerPage) {
                lastPage.slots.push(null);
            }
        }
    }

    // Pad final page if needed
    if (bookPages.length > 0) {
        const lastPage = bookPages[bookPages.length - 1];
        while (lastPage.slots.length < slotsPerPage) {
            lastPage.slots.push(null);
        }
    }

    // Update stats
    const totalCards = expanded.length;
    const totalPages = bookPages.length;
    document.getElementById("book-stats").textContent = `${totalCards} cards · ${totalPages} pages`;
}

function renderBookSpread() {
    const spread = document.getElementById("book-spread");
    const leftIdx = bookCurrentSpread * 2;
    const rightIdx = leftIdx + 1;

    let html = "";

    // Left page
    if (leftIdx < bookPages.length) {
        html += renderBookPage(bookPages[leftIdx]);
    }
    // Right page
    if (rightIdx < bookPages.length) {
        html += renderBookPage(bookPages[rightIdx]);
    }

    spread.innerHTML = html;

    // Page navigation
    const totalSpreads = Math.ceil(bookPages.length / 2);
    document.getElementById("book-page-num").textContent =
        bookPages.length > 0
            ? `${bookCurrentSpread + 1} / ${totalSpreads}`
            : "No cards";
    document.getElementById("book-prev").disabled = bookCurrentSpread <= 0;
    document.getElementById("book-next").disabled = bookCurrentSpread >= totalSpreads - 1;

    // Card click handlers
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
                return price ? `<span class="book-slot-price">${Number(price).toFixed(2)}€</span>` : "";
            })() : "";
            return `<div class="book-slot" data-id="${card.id}"><img src="${card.image_url || ""}" alt="${card.name}" title="${card.name}&#10;${card.set_code || ""} · ${card.rarity} · ${card.lang}" loading="lazy">${priceTag}</div>`;
        })
        .join("");
    return `<div class="book-page">${header}<div class="book-page-grid" style="grid-template-columns:repeat(${cols},1fr)">${slots}</div></div>`;
}

// Book event listeners
["book-group-by", "book-sort-by", "book-new-page", "book-grid-size", "book-max-copies",
 "book-filter-lang", "book-filter-condition", "book-filter-set", "book-min-price", "book-show-prices"
].forEach(id => {
    document.getElementById(id).addEventListener("change", buildAndRenderBook);
});
// Also rebuild on price input blur (min price)
document.getElementById("book-min-price").addEventListener("input", buildAndRenderBook);
document.getElementById("book-prev").addEventListener("click", () => {
    if (bookCurrentSpread > 0) { bookCurrentSpread--; renderBookSpread(); }
});
document.getElementById("book-next").addEventListener("click", () => {
    if ((bookCurrentSpread + 1) * 2 < bookPages.length) { bookCurrentSpread++; renderBookSpread(); }
});

// Persist book preferences
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
function loadBookPrefs() {
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

// --- Extension Status ---
const extStatusBtn = document.getElementById("ext-status-btn");

async function checkExtensionStatus() {
    extStatusBtn.className = "ext-status-dot checking";
    extStatusBtn.title = "Extension: checking...";
    try {
        const resp = await fetch(`${API}/api/extension/status`);
        if (resp.ok) {
            const data = await resp.json();
            if (data.connected) {
                extStatusBtn.className = "ext-status-dot connected";
                extStatusBtn.title = "Extension: connected";
            } else {
                extStatusBtn.className = "ext-status-dot disconnected";
                extStatusBtn.title = "Extension: disconnected (click to retry)";
            }
        } else {
            extStatusBtn.className = "ext-status-dot disconnected";
            extStatusBtn.title = "Extension: error";
        }
    } catch (e) {
        extStatusBtn.className = "ext-status-dot disconnected";
        extStatusBtn.title = "Extension: server unreachable";
    }
}

extStatusBtn.addEventListener("click", checkExtensionStatus);
// Poll every 30s
setInterval(checkExtensionStatus, 30000);

// --- Init ---
loadSettings().then(() => {
    priceSelect.value = priceDisplayMode;
    loadBookPrefs();
    loadCollection();
    checkExtensionStatus();
});
