// =============================================
// Scanner view — camera, preview, scan, results
// =============================================

import { API, cardImgUrl, showToast } from "./shared.js";
import { openAddModal } from "./collection.js";

let currentStream = null;
let previewInterval = null;
let previewBusy = false;
let autoScanName = "";
let autoScanCount = 0;
let autoScanTriggered = false;
const AUTO_SCAN_THRESHOLD = 0.60;
const AUTO_SCAN_FRAMES = 4;

let lastDetectedMode = "no_card";
let lastDetectedName = "";
let lastDetectedConf = 0;
let noCardFrames = 0;
const NO_CARD_GRACE = 3;

export function switchToView(viewId) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.getElementById(`view-${viewId}`).classList.add("active");
    document.querySelectorAll(".nav-btn").forEach((b) => {
        b.classList.toggle("active", b.dataset.view === viewId);
    });
}

export function switchToScanner() {
    switchToView("scanner");
    resetScanner();
}

export function resetScanner() {
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

export function stopCamera() {
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
    if (data.mode === "no_card" || data.mode === "no_image") {
        noCardFrames++;
        autoScanName = "";
        autoScanCount = 0;
        if (noCardFrames < NO_CARD_GRACE && lastDetectedMode === "detected") return;
        lastDetectedMode = "no_card";
        _updatePreviewStatus(container, null, 0);
        _updatePreviewDebug(container, data);
        return;
    }
    noCardFrames = 0;
    lastDetectedMode = "detected";
    const hasHash = data.hash_match_name && data.hash_match_name.length > 0;
    const conf = data.hash_match_confidence || 0;
    if (hasHash) {
        lastDetectedName = data.hash_match_name;
        lastDetectedConf = conf;
    }
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
    const details = container.querySelector("#preview-debug");
    if (!details || !details.open) return;
    const artwork = document.getElementById("pv-dbg-artwork");
    const warped = document.getElementById("pv-dbg-warped");
    const detect = document.getElementById("pv-dbg-detect");
    if (data.artwork_debug) { artwork.src = "data:image/jpeg;base64," + data.artwork_debug; artwork.hidden = false; }
    if (data.warped_image) { warped.src = "data:image/jpeg;base64," + data.warped_image; warped.hidden = false; }
    if (data.debug_image) { detect.src = "data:image/jpeg;base64," + data.debug_image; detect.hidden = false; }
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
    // Fast path: single high-confidence match
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
            .map((card) => {
                const cardForAdd = { ...card };
                const setsJson = JSON.stringify(card.sets || []).replace(/'/g, "&#39;");
                delete cardForAdd.sets;
                return `
            <div class="card-item scan-result-card">
                <img src="${cardImgUrl(card.image_url)}" alt="${card.name}" loading="lazy">
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
}

document.getElementById("back-to-camera").addEventListener("click", () => {
    switchToScanner();
});
