// =============================================
// Collection view — grid, filters, card modal, split, add, search
// =============================================

import {
    API, allCollectionCards, setAllCollectionCards,
    currentModalCardId, setCurrentModalCardId,
    currentModalCard, setCurrentModalCard,
    pendingModalSaves,
    RARITY_OPTIONS, TYPE_GROUP, TYPE_ORDER,
    langFlag, cardImgUrl, getDisplayPrice, showToast,
    buildCardmarketUrl, detectLangFromSetCode,
} from "./shared.js";

// --- Collection loading & filters ---

export async function loadCollection() {
    try {
        const params = new URLSearchParams();
        const rarity = document.getElementById("filter-rarity").value;
        const condition = document.getElementById("filter-condition").value;
        const lang = document.getElementById("filter-lang").value;
        if (rarity) params.set("rarity", rarity);
        if (condition) params.set("condition", condition);
        if (lang) params.set("lang", lang);

        const resp = await fetch(`${API}/api/cards?${params}`);
        setAllCollectionCards(await resp.json());
        updateCollectionFilters(allCollectionCards);
        applyLocalFilters();
    } catch (e) {
        console.error("Failed to load collection:", e);
    }
}

function _rebuildFilterSelect(id, label, values) {
    const select = document.getElementById(id);
    const current = select.value;
    select.innerHTML = `<option value="">All ${label}</option>`;
    values.forEach((v) => {
        const opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v;
        if (v === current) opt.selected = true;
        select.appendChild(opt);
    });
}

function updateCollectionFilters(cards) {
    const rarities = [...new Set(cards.map((c) => c.rarity))].sort();
    _rebuildFilterSelect("filter-rarity", "rarities", rarities);

    const archetypes = [...new Set(cards.map((c) => c.archetype).filter(Boolean))].sort();
    _rebuildFilterSelect("filter-archetype", "archetypes", archetypes);

    const sets = [...new Set(cards.map((c) => c.set_code ? c.set_code.split("-")[0] : "").filter(Boolean))].sort();
    _rebuildFilterSelect("filter-set", "sets", sets);

    const types = [...new Set(cards.map((c) => TYPE_GROUP[c.type] || c.type).filter(Boolean))].sort((a, b) => {
        return (TYPE_ORDER[a] ?? 99) - (TYPE_ORDER[b] ?? 99);
    });
    _rebuildFilterSelect("filter-type", "types", types);

    const levels = [...new Set(cards.map((c) => c.level).filter((l) => l != null))].sort((a, b) => a - b);
    _rebuildFilterSelect("filter-level", "levels", levels.map(String));

    const locations = [...new Set(cards.flatMap((c) => c.location || []))].sort();
    _rebuildFilterSelect("filter-location", "locations", locations);
}

["filter-rarity", "filter-condition", "filter-lang"].forEach((id) => {
    document.getElementById(id).addEventListener("change", loadCollection);
});
["filter-archetype", "filter-set", "filter-type", "filter-level", "filter-location"].forEach((id) => {
    document.getElementById(id).addEventListener("change", applyLocalFilters);
});

function applyLocalFilters() {
    const q = document.getElementById("search-input").value.trim().toLowerCase();
    const archetype = document.getElementById("filter-archetype").value;
    const set = document.getElementById("filter-set").value;
    const type = document.getElementById("filter-type").value;
    const level = document.getElementById("filter-level").value;
    const location = document.getElementById("filter-location").value;

    const cards = allCollectionCards.filter((c) => {
        if (q && !c.name.toLowerCase().includes(q) && !(c.set_code && c.set_code.toLowerCase().includes(q))) return false;
        if (archetype && c.archetype !== archetype) return false;
        if (set && !(c.set_code || "").startsWith(set + "-") && !(c.set_code || "").startsWith(set)) return false;
        if (type && (TYPE_GROUP[c.type] || c.type) !== type) return false;
        if (level && c.level !== parseInt(level)) return false;
        if (location && !(c.location || []).includes(location)) return false;
        return true;
    });
    renderCollection(cards);
}

// Restore sort from localStorage
const sortSelect = document.getElementById("sort-select");
const savedSort = localStorage.getItem("yugipy_collection_sort");
if (savedSort && [...sortSelect.options].some((o) => o.value === savedSort)) {
    sortSelect.value = savedSort;
}
sortSelect.addEventListener("change", () => {
    localStorage.setItem("yugipy_collection_sort", sortSelect.value);
    applyLocalFilters();
});

document.getElementById("search-input").addEventListener("input", applyLocalFilters);

// --- Rendering ---

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

    const sortBy = document.getElementById("sort-select").value;
    const sorted = [...cards];
    switch (sortBy) {
        case "name-asc": sorted.sort((a, b) => a.name.localeCompare(b.name)); break;
        case "name-desc": sorted.sort((a, b) => b.name.localeCompare(a.name)); break;
        case "price-desc": sorted.sort((a, b) => (getDisplayPrice(b).price || 0) - (getDisplayPrice(a).price || 0)); break;
        case "price-asc": sorted.sort((a, b) => (getDisplayPrice(a).price || 0) - (getDisplayPrice(b).price || 0)); break;
        case "qty-desc": sorted.sort((a, b) => b.quantity - a.quantity); break;
        case "type": sorted.sort((a, b) => {
            const aO = TYPE_ORDER[TYPE_GROUP[a.type] || a.type] ?? 99;
            const bO = TYPE_ORDER[TYPE_GROUP[b.type] || b.type] ?? 99;
            return aO - bO || (b.level ?? 0) - (a.level ?? 0) || a.name.localeCompare(b.name);
        }); break;
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
                <img src="${cardImgUrl(card.image_url)}" alt="${card.name}" loading="lazy">
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

export { renderCollection };

// --- Card Detail Modal ---
let modalImages = [];
let modalImageIndex = 0;

async function _fetchCardImages(cardName) {
    try {
        const resp = await fetch(`https://db.ygoprodeck.com/api/v7/cardinfo.php?name=${encodeURIComponent(cardName)}`);
        if (!resp.ok) return [];
        const data = await resp.json();
        return data.data?.[0]?.card_images || [];
    } catch { return []; }
}

function _updateModalImgUI() {
    const prevBtn = document.getElementById("modal-img-prev");
    const nextBtn = document.getElementById("modal-img-next");
    const counter = document.getElementById("modal-img-counter");
    const hasMultiple = modalImages.length > 1;
    prevBtn.hidden = !hasMultiple;
    nextBtn.hidden = !hasMultiple;
    counter.hidden = !hasMultiple;
    if (hasMultiple) {
        counter.textContent = `${modalImageIndex + 1} / ${modalImages.length}`;
    }
}

function _switchModalImage(delta) {
    if (modalImages.length <= 1) return;
    modalImageIndex = (modalImageIndex + delta + modalImages.length) % modalImages.length;
    const newUrl = modalImages[modalImageIndex];
    document.getElementById("modal-img").src = newUrl;
    _updateModalImgUI();
    if (currentModalCard) {
        currentModalCard.image_url = newUrl;
        fetch(`${API}/api/cards/${currentModalCardId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_url: newUrl }),
        });
    }
}

document.getElementById("modal-img-prev").addEventListener("click", () => _switchModalImage(-1));
document.getElementById("modal-img-next").addEventListener("click", () => _switchModalImage(1));

export async function openCardModal(id, cards) {
    let card = cards.find((c) => c.id === id);
    if (!card) return;

    setCurrentModalCardId(id);
    setCurrentModalCard(card);
    const modal = document.getElementById("card-modal");
    const imgEl = document.getElementById("modal-img");
    imgEl.src = cardImgUrl(card.image_url);
    modal.hidden = false;

    modalImages = [cardImgUrl(card.image_url)];
    modalImageIndex = 0;
    _updateModalImgUI();

    _fetchCardImages(card.name).then((images) => {
        if (currentModalCardId !== id) return;
        if (images.length > 1) {
            modalImages = images.map((i) => cardImgUrl(i.image_url));
            const idx = modalImages.indexOf(cardImgUrl(card.image_url));
            modalImageIndex = idx >= 0 ? idx : 0;
            _updateModalImgUI();
        }
    });

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
                <span title="Minimum">Min: <strong id="modal-cm-min">${card.price_cm_min != null ? Number(card.price_cm_min).toFixed(2) + "\u20AC" : "\u2014"}</strong></span>
                <span title="Average top 5">Avg: <strong id="modal-cm-avg">${card.price_cm_avg != null ? Number(card.price_cm_avg).toFixed(2) + "\u20AC" : "\u2014"}</strong></span>
                <span title="Median top 5">Med: <strong id="modal-cm-median">${card.price_cm_median != null ? Number(card.price_cm_median).toFixed(2) + "\u20AC" : "\u2014"}</strong></span>
            </div>
            <a href="${cmSearchUrl}" target="_blank" rel="noopener" id="modal-cardmarket-link" class="cardmarket-link">View on Cardmarket \u2197</a>
        </div>
    `;

    const condOpts = ["Mint","Near Mint","Excellent","Good","Light Played","Played","Poor"];
    const langOpts = [["IT","Italian"],["EN","English"],["FR","French"],["DE","German"],["ES","Spanish"],["PT","Portuguese"],["JA","Japanese"],["KO","Korean"]];

    const infoEl = document.getElementById("modal-collection-info");
    infoEl.innerHTML = `
        <div class="form-row">
            <div class="form-group" style="flex:2">
                <label>Rarity</label>
                <select id="modal-edit-rarity">
                    ${RARITY_OPTIONS.map((r) => `<option value="${r}" ${r === card.rarity ? "selected" : ""}>${r}</option>`).join("")}
                    ${!RARITY_OPTIONS.includes(card.rarity) ? `<option value="${card.rarity}" selected>${card.rarity}</option>` : ""}
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
                const otherOpt = document.createElement("option");
                otherOpt.value = "__other__";
                otherOpt.textContent = "Other...";
                setSelect.appendChild(otherOpt);
                if (!card.set_code) {
                    const emptyOpt = document.createElement("option");
                    emptyOpt.value = "";
                    emptyOpt.textContent = "\u2014 Select \u2014";
                    emptyOpt.selected = true;
                    setSelect.prepend(emptyOpt);
                }
                const matchedSet = apiSets.find(s => s.set_code === card.set_code);
                if (matchedSet) {
                    const cmLink = document.getElementById("modal-cardmarket-link");
                    if (cmLink) cmLink.href = buildCardmarketUrl(card.name, matchedSet.set_name, card.rarity, card.lang, card.set_code);
                }
            } else {
                setSelect.hidden = true;
                setInput.hidden = false;
            }
        } catch (e) {
            setSelect.hidden = true;
            setInput.hidden = false;
        }
    })();

    // Auto-save on change
    pendingModalSaves.length = 0;
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
            if (updated.id !== id) {
                document.getElementById("card-modal").hidden = true;
                loadCollection();
            }
        } catch (e) { console.error(e); }
    };

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

    // Price manual edit
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

    // Cardmarket price refresh
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
                showToast(parts.join(" \u00B7 ") || "No price found");
            }
        } catch (e) { console.error(e); showToast("Connection error", "error"); }
        btn.disabled = false;
        btn.textContent = "CM";
    });

    document.getElementById("modal-quantity").textContent = `x${card.quantity}`;
    document.getElementById("modal-split").style.display = card.quantity > 1 ? "" : "none";

    // Auto-fetch price if older than 7 days
    const PRICE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
    const priceAge = card.price_updated_at ? Date.now() - new Date(card.price_updated_at).getTime() : Infinity;
    if (priceAge > PRICE_MAX_AGE_MS && !card.price_manual) {
        document.getElementById("modal-cm-price").click();
    }
}

// Quantity buttons
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
    } catch (e) { console.error(e); }
    return null;
}

// Delete
document.getElementById("modal-delete").addEventListener("click", async () => {
    if (!confirm("Remove this card from the collection?")) return;
    try {
        await fetch(`${API}/api/cards/${currentModalCardId}`, { method: "DELETE" });
        document.getElementById("card-modal").hidden = true;
        loadCollection();
    } catch (e) { console.error(e); }
});

// --- Split ---
document.getElementById("modal-split").addEventListener("click", () => {
    if (!currentModalCard) return;
    const card = currentModalCard;
    document.getElementById("split-info").innerHTML =
        `${card.name} \u2014 currently x${card.quantity} (${card.rarity}, ${card.condition}) ${langFlag(card.lang)}`;
    document.getElementById("split-qty").value = 1;
    document.getElementById("split-qty").max = card.quantity - 1;
    const splitRarity = document.getElementById("split-rarity");
    splitRarity.innerHTML = document.getElementById("add-rarity").innerHTML;
    splitRarity.value = card.rarity;
    document.getElementById("split-condition").value = card.condition;
    document.getElementById("split-lang").value = card.lang;
    document.getElementById("split-set-code").value = card.set_code || "";
    document.getElementById("split-modal").hidden = false;
});

document.getElementById("split-confirm").addEventListener("click", async () => {
    if (!currentModalCardId) return;
    const qty = parseInt(document.getElementById("split-qty").value) || 1;
    const rarity = document.getElementById("split-rarity").value;
    const condition = document.getElementById("split-condition").value;
    const lang = document.getElementById("split-lang").value;
    const setCode = document.getElementById("split-set-code").value.trim() || null;
    try {
        const resp = await fetch(`${API}/api/cards/${currentModalCardId}/split`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ quantity: qty, rarity, condition, lang, set_code: setCode }),
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
    } catch (e) { console.error(e); }
});

// --- Close modals ---
function _handleModalClose(modal) {
    modal.hidden = true;
    if (modal.id === "card-modal") {
        Promise.all(pendingModalSaves).then(() => {
            pendingModalSaves.length = 0;
            loadCollection();
        });
    }
    if (modal.id === "add-modal" && document.getElementById("view-scanner").classList.contains("active")) {
        import("./scanner.js").then(m => { m.resetScanner(); });
    }
}

document.querySelectorAll(".modal-close").forEach((btn) => {
    btn.addEventListener("click", () => {
        _handleModalClose(btn.closest(".modal"));
    });
});

document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", () => {
        _handleModalClose(backdrop.closest(".modal"));
    });
});

// --- Add card modal ---
let pendingCardData = null;
let pendingCardSets = null;

export function openAddModal(cardData, sets) {
    document.querySelectorAll(".modal").forEach((m) => { m.hidden = true; });
    pendingCardData = cardData;
    pendingCardSets = sets;

    document.getElementById("add-modal-img").src = cardImgUrl(cardData.image_url);
    document.getElementById("add-modal-name").textContent = cardData.name;
    document.getElementById("add-modal-type").textContent = cardData.type;

    const select = document.getElementById("add-set-select");
    select.innerHTML = "";
    if (sets && sets.length > 0) {
        sets.forEach((s) => {
            const opt = document.createElement("option");
            opt.value = JSON.stringify({ set_code: s.set_code, set_rarity: s.set_rarity, set_name: s.set_name, set_price: s.set_price || null });
            const priceStr = s.set_price ? ` \u2014 ${s.set_price}\u20AC` : "";
            opt.textContent = `${s.set_code} \u2014 ${s.set_name} (${s.set_rarity})${priceStr}`;
            select.appendChild(opt);
        });
    } else {
        const opt = document.createElement("option");
        opt.value = JSON.stringify({ set_code: "N/A", set_rarity: "Common", set_name: "Unknown" });
        opt.textContent = "No expansion found";
        select.appendChild(opt);
    }

    const raritySelect = document.getElementById("add-rarity");
    function syncRarity() {
        try {
            const setData = JSON.parse(select.value);
            const rarity = setData.set_rarity || "Common";
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
    syncRarity();

    const detectedSetCode = sets?.length ? sets[0].set_code : "";
    const detectedLang = detectLangFromSetCode(detectedSetCode);
    const lastLang = localStorage.getItem("yugipy_last_lang") || "IT";
    document.getElementById("add-lang").value = detectedLang || lastLang;

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
    const setData = JSON.parse(document.getElementById("add-set-select").value);
    const cardDataWithPrice = { ...pendingCardData };
    if (setData.set_price && setData.set_price > 0) {
        cardDataWithPrice.price_cardmarket = setData.set_price;
    }
    const payload = {
        ...cardDataWithPrice,
        set_code: (setData.set_code && setData.set_code !== "N/A") ? setData.set_code : null,
        rarity, condition, lang, location,
        quantity: parseInt(document.getElementById("add-qty").value) || 1,
    };
    try {
        const resp = await fetch(`${API}/api/cards`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (resp.ok) {
            localStorage.setItem("yugipy_last_lang", lang);
            localStorage.setItem("yugipy_last_condition", condition);
            showToast("Card added to collection!");
            // Save training crop if available (from scanner)
            import("./scanner.js").then(m => {
                const crop = m.getLastScanCrop();
                if (crop && pendingCardData.card_id) {
                    const form = new FormData();
                    form.append("file", crop, "crop.jpg");
                    form.append("card_id", String(pendingCardData.card_id));
                    fetch(`${API}/api/save-training-crop`, { method: "POST", body: form }).catch(() => {});
                }
            });
            document.getElementById("add-modal").hidden = true;
            loadCollection();
            if (document.getElementById("view-scanner").classList.contains("active")
                || !document.querySelector(".view.active")) {
                import("./scanner.js").then(m => { m.switchToScanner(); });
            }
        } else {
            const err = await resp.json();
            alert(err.detail || "Error adding card");
        }
    } catch (e) { console.error(e); }
});

// --- Manual search (YGOProDeck) ---
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
                    <img src="${cardImgUrl(card.image_url)}" alt="${card.name}" loading="lazy">
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
    } catch (e) { console.error(e); }
}

// Populate rarity dropdown
const addRaritySelect = document.getElementById("add-rarity");
RARITY_OPTIONS.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r;
    opt.textContent = r;
    addRaritySelect.appendChild(opt);
});
