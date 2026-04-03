// =============================================
// Settings view — setup wizard, price display, bulk sync, extension status
// =============================================

import { API, priceDisplayMode, setPriceDisplayMode, saveSetting, showToast } from "./shared.js";
import { loadCollection, renderCollection } from "./collection.js";

// --- Price Display Setting ---
export const priceSelect = document.getElementById("setting-price-display");
priceSelect.value = priceDisplayMode;
priceSelect.addEventListener("change", () => {
    setPriceDisplayMode(priceSelect.value);
    saveSetting("priceDisplay", priceSelect.value);
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
        if (state === "done") icon.textContent = "\u25CF";
        else if (state === "active") icon.textContent = "\u25C9";
        else icon.textContent = "\u25CB";
    }

    function resetSteps() { for (let i = 1; i <= 4; i++) setStepState(i, ""); }

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
            if (d.type === "info") progressText.textContent = d.message;
            if (d.type === "progress") {
                if (d.total > 0) {
                    const pct = Math.round((d.done / d.total) * 100);
                    bar.style.width = `${pct}%`;
                    let text = `${d.done}/${d.total}`;
                    if (d.failed) text += ` (${d.failed} failed)`;
                    if (d.skipped) text += ` (${d.skipped} skipped)`;
                    progressText.textContent = d.message || text;
                } else if (d.message) progressText.textContent = d.message;
            }
            if (d.type === "done") {
                evtSource.close();
                setStepState(currentStep, "done");
                bar.style.width = "100%";
                bar.style.background = "#4caf50";
                progressText.textContent = "Setup complete!";
                cancelBtn.hidden = true;
                showToast("Card index configured!");
                setTimeout(() => { wizard.hidden = true; loadStatus(); }, 3000);
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
        setTimeout(() => { cancelBtn.disabled = false; cancelBtn.textContent = "Cancel"; }, 3000);
    });
    loadStatus();
})();

// --- Image Download ---
document.getElementById("img-download-btn").addEventListener("click", () => {
    const btn = document.getElementById("img-download-btn");
    const progressEl = document.getElementById("img-download-progress");
    const bar = document.getElementById("img-download-bar");
    const status = document.getElementById("img-download-status");
    btn.disabled = true;
    btn.textContent = "Downloading...";
    progressEl.hidden = false;
    bar.style.width = "0%";
    status.textContent = "Starting...";

    const es = new EventSource(`${API}/api/setup/download-images`);
    es.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.error) {
            status.textContent = `Error: ${msg.error}`;
            es.close(); btn.disabled = false; btn.textContent = "Download missing images";
            return;
        }
        if (msg.type === "info") status.textContent = msg.message;
        else if (msg.type === "progress") {
            const pct = msg.total ? ((msg.done / msg.total) * 100).toFixed(1) : 0;
            bar.style.width = `${pct}%`;
            status.textContent = `${msg.done} / ${msg.total} (${msg.ok} ok, ${msg.failed} failed)`;
        } else if (msg.type === "done") {
            status.textContent = msg.message;
            es.close(); btn.disabled = false; btn.textContent = "Download missing images";
        } else if (msg.type === "cancelled") {
            status.textContent = "Cancelled";
            es.close(); btn.disabled = false; btn.textContent = "Download missing images";
        }
    };
    es.onerror = () => { es.close(); status.textContent = "Connection lost"; btn.disabled = false; btn.textContent = "Download missing images"; };
});

// --- Cardmarket Bulk Sync ---
let bulkPollTimer = null;

document.getElementById("cm-bulk-start").addEventListener("click", async () => {
    const resp = await fetch(`${API}/api/cm-bulk/start`, { method: "POST" });
    const data = await resp.json();
    if (data.error === "extension_not_connected") { showToast("Firefox extension not connected", "error"); return; }
    if (data.error === "already_running") { showToast("Sync already running", "error"); return; }
    document.getElementById("cm-bulk-start").hidden = true;
    document.getElementById("cm-bulk-stop").hidden = false;
    document.getElementById("cm-bulk-progress").hidden = false;
    document.getElementById("cm-bulk-failed").hidden = true;
    startBulkPoll();
});

document.getElementById("cm-bulk-stop").addEventListener("click", async () => {
    const btn = document.getElementById("cm-bulk-stop");
    btn.disabled = true; btn.textContent = "Stopping..."; btn.style.background = "#ffa726";
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
            stopBtn.hidden = true; stopBtn.disabled = false; stopBtn.textContent = "Stop"; stopBtn.style.background = "#e53935";
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

// --- Extension Status ---
const extStatusBtn = document.getElementById("ext-status-btn");

export async function checkExtensionStatus() {
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
setInterval(checkExtensionStatus, 30000);
