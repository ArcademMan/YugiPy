// =============================================
// YugiPy — App entry point
// =============================================

import * as shared from "./shared.js";
import { loadCollection } from "./collection.js";
import { switchToView, resetScanner, stopCamera } from "./scanner.js";
import { loadBook, loadBookPrefs } from "./book.js";
import { loadStats } from "./stats.js";
import { priceSelect, checkExtensionStatus } from "./settings.js";

// --- Navigation ---
function navigateTo(viewId) {
    switchToView(viewId);
    localStorage.setItem("yugipy_activeView", viewId);

    if (viewId === "scanner") {
        resetScanner();
    } else {
        stopCamera();
        if (viewId === "collection") loadCollection();
        if (viewId === "book") loadBook();
        if (viewId === "stats") loadStats();
    }
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => navigateTo(btn.dataset.view));
});

// --- Init ---
(async () => {
    await shared.loadSettings();
    priceSelect.value = shared.priceDisplayMode;
    loadBookPrefs();

    const saved = localStorage.getItem("yugipy_activeView");
    if (saved && document.getElementById(`view-${saved}`)) {
        navigateTo(saved);
    } else {
        loadCollection();
    }

    checkExtensionStatus();
})();
