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
document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        switchToView(btn.dataset.view);

        if (btn.dataset.view === "scanner") {
            resetScanner();
        } else {
            stopCamera();
            if (btn.dataset.view === "collection") loadCollection();
            if (btn.dataset.view === "book") loadBook();
            if (btn.dataset.view === "stats") loadStats();
        }
    });
});

// --- Init ---
(async () => {
    await shared.loadSettings();
    priceSelect.value = shared.priceDisplayMode;
    loadBookPrefs();
    loadCollection();
    checkExtensionStatus();
})();
