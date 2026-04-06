// =============================================
// Statistics view — charts and KPIs
// =============================================

import { API, cardImgUrl } from "./shared.js";

let _statsCharts = {};

function _destroyCharts() {
    Object.values(_statsCharts).forEach(c => c.destroy());
    _statsCharts = {};
}

const CHART_COLORS = [
    "#7c5cfc", "#22c55e", "#ef4444", "#3b82f6", "#eab308", "#f97316",
    "#06b6d4", "#ec4899", "#8b5cf6", "#14b8a6", "#f43f5e", "#a855f7",
    "#0ea5e9", "#84cc16", "#d946ef", "#fbbf24", "#6366f1", "#10b981",
    "#e11d48", "#059669",
];

const ATTR_COLORS = {
    DARK: "#9333ea", LIGHT: "#fbbf24", FIRE: "#ef4444", WATER: "#3b82f6",
    EARTH: "#a16207", WIND: "#22c55e", DIVINE: "#f59e0b",
};

const COND_COLORS = {
    "Mint": "#00bcd4", "Near Mint": "#4caf50", "Excellent": "#8bc34a",
    "Good": "#fdd835", "Light Played": "#ff9800", "Played": "#ff5722", "Poor": "#f44336",
};

function _chartDefaults() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: { color: "#9ca3af", font: { family: "'Inter', sans-serif", size: 11 } },
            },
        },
    };
}

function _doughnut(canvasId, labels, data, colors) {
    const ctx = document.getElementById(canvasId);
    _statsCharts[canvasId] = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: colors || labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
                borderColor: "rgba(0,0,0,0.3)",
                borderWidth: 1,
            }],
        },
        options: {
            ..._chartDefaults(),
            cutout: "55%",
            plugins: {
                ..._chartDefaults().plugins,
                legend: {
                    position: "right",
                    labels: { color: "#9ca3af", font: { family: "'Inter', sans-serif", size: 11 }, padding: 8 },
                },
            },
        },
    });
}

function _bar(canvasId, labels, data, color, label) {
    const ctx = document.getElementById(canvasId);
    _statsCharts[canvasId] = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: label || "",
                data,
                backgroundColor: typeof color === "string" ? color : labels.map((_, i) => (color || CHART_COLORS)[i % (color || CHART_COLORS).length]),
                borderRadius: 4,
            }],
        },
        options: {
            ..._chartDefaults(),
            indexAxis: "x",
            plugins: { ..._chartDefaults().plugins, legend: { display: false } },
            scales: {
                x: { ticks: { color: "#6b7280", font: { size: 10 } }, grid: { color: "rgba(255,255,255,0.04)" } },
                y: { ticks: { color: "#6b7280" }, grid: { color: "rgba(255,255,255,0.04)" } },
            },
        },
    });
}

function _horizontalBar(canvasId, labels, data, colors) {
    const ctx = document.getElementById(canvasId);
    const barHeight = 28;
    const minHeight = 200;
    const neededHeight = Math.max(minHeight, labels.length * barHeight + 40);
    const wrapper = ctx.parentElement;
    wrapper.style.height = neededHeight + "px";

    _statsCharts[canvasId] = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: colors || labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
                borderRadius: 4,
            }],
        },
        options: {
            ..._chartDefaults(),
            indexAxis: "y",
            plugins: { ..._chartDefaults().plugins, legend: { display: false } },
            scales: {
                x: { ticks: { color: "#6b7280" }, grid: { color: "rgba(255,255,255,0.04)" } },
                y: { ticks: { color: "#9ca3af", font: { size: 11 }, autoSkip: false }, grid: { display: false } },
            },
        },
    });
}

export async function loadStats() {
    const loading = document.getElementById("stats-loading");
    const empty = document.getElementById("stats-empty");
    const content = document.getElementById("stats-content");
    loading.hidden = false;
    empty.hidden = true;
    content.hidden = true;

    try {
        const resp = await fetch(`${API}/api/stats`);
        const stats = await resp.json();
        loading.hidden = true;

        if (stats.empty) { empty.hidden = false; return; }

        content.hidden = false;
        _destroyCharts();

        const ov = stats.overview;
        document.getElementById("kpi-total-value").textContent = `${ov.total_value.toFixed(2)}\u20AC`;
        document.getElementById("kpi-unique").textContent = ov.total_unique.toLocaleString();
        document.getElementById("kpi-copies").textContent = ov.total_copies.toLocaleString();
        document.getElementById("kpi-distinct").textContent = ov.distinct_cards.toLocaleString();
        document.getElementById("kpi-avg-value").textContent = `${ov.avg_card_value.toFixed(2)}\u20AC`;
        document.getElementById("kpi-priced").textContent = `${ov.priced_count} / ${ov.unpriced_count}`;

        // Top valuable
        const topList = document.getElementById("top-valuable-list");
        topList.innerHTML = stats.top_valuable.map((c, i) => `
            <div class="top-valuable-item">
                <span class="tv-rank">#${i + 1}</span>
                <img class="tv-img" src="${cardImgUrl(c.image_url)}" alt="${c.name}" loading="lazy">
                <div class="tv-info">
                    <div class="tv-name">${c.name}</div>
                    <div class="tv-meta">${c.set_code || ""} &middot; ${c.rarity}</div>
                </div>
                <div class="tv-price-col">
                    <div class="tv-price">${c.price.toFixed(2)}\u20AC</div>
                    ${c.quantity > 1 ? `<div class="tv-qty">x${c.quantity} = ${c.total_value.toFixed(2)}\u20AC</div>` : ""}
                </div>
            </div>
        `).join("");

        // Doughnut charts
        const dist = stats.distributions;
        _doughnut("chart-rarity", Object.keys(dist.rarity), Object.values(dist.rarity));
        _doughnut("chart-type", Object.keys(dist.type), Object.values(dist.type));
        _doughnut("chart-condition",
            Object.keys(dist.condition), Object.values(dist.condition),
            Object.keys(dist.condition).map(k => COND_COLORS[k] || CHART_COLORS[0]));
        _doughnut("chart-lang", Object.keys(dist.language), Object.values(dist.language));
        _doughnut("chart-attribute",
            Object.keys(dist.attribute), Object.values(dist.attribute),
            Object.keys(dist.attribute).map(k => ATTR_COLORS[k] || CHART_COLORS[0]));
        _doughnut("chart-race", Object.keys(dist.race), Object.values(dist.race));

        // Bar charts
        const rarityLabels = Object.keys(stats.value_by_rarity).map(k => `${k} (${stats.count_by_rarity[k] || 0})`);
        _horizontalBar("chart-value-rarity", rarityLabels, Object.values(stats.value_by_rarity));
        const avgRarityLabels = Object.keys(stats.avg_by_rarity).map(k => `${k} (${stats.count_by_rarity[k] || 0})`);
        _horizontalBar("chart-avg-rarity", avgRarityLabels, Object.values(stats.avg_by_rarity));
        _horizontalBar("chart-value-lang", Object.keys(stats.value_by_lang), Object.values(stats.value_by_lang));
        _bar("chart-price-dist", Object.keys(stats.price_distribution), Object.values(stats.price_distribution), "#7c5cfc");
        _bar("chart-level", Object.keys(dist.level).map(l => `Lv ${l}`), Object.values(dist.level), "#3b82f6");
        _horizontalBar("chart-sets", Object.keys(dist.set), Object.values(dist.set));
        _horizontalBar("chart-archetypes", Object.keys(dist.archetype), Object.values(dist.archetype));

        // ATK/DEF scatter
        const scatterCtx = document.getElementById("chart-atk-def");
        _statsCharts["chart-atk-def"] = new Chart(scatterCtx, {
            type: "scatter",
            data: {
                datasets: [{
                    label: "Monsters",
                    data: stats.atk_def_scatter.map(m => ({ x: m.atk, y: m.def, name: m.name })),
                    backgroundColor: "rgba(124, 92, 252, 0.5)",
                    borderColor: "#7c5cfc",
                    pointRadius: 3,
                    pointHoverRadius: 6,
                }],
            },
            options: {
                ..._chartDefaults(),
                plugins: {
                    ..._chartDefaults().plugins,
                    legend: { display: false },
                    tooltip: { callbacks: { label: ctx => `${ctx.raw.name}: ATK ${ctx.raw.x} / DEF ${ctx.raw.y}` } },
                },
                scales: {
                    x: { title: { display: true, text: "ATK", color: "#6b7280" }, ticks: { color: "#6b7280" }, grid: { color: "rgba(255,255,255,0.04)" } },
                    y: { title: { display: true, text: "DEF", color: "#6b7280" }, ticks: { color: "#6b7280" }, grid: { color: "rgba(255,255,255,0.04)" } },
                },
            },
        });

        // Growth
        const months = Object.keys(stats.growth_by_month);
        const growthData = Object.values(stats.growth_by_month);
        const cumulative = [];
        growthData.reduce((acc, val, i) => { cumulative[i] = acc + val; return cumulative[i]; }, 0);

        const growthCtx = document.getElementById("chart-growth");
        _statsCharts["chart-growth"] = new Chart(growthCtx, {
            type: "line",
            data: {
                labels: months,
                datasets: [
                    { label: "Cumulative", data: cumulative, borderColor: "#7c5cfc", backgroundColor: "rgba(124, 92, 252, 0.1)", fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: "#7c5cfc" },
                    { label: "Added", data: growthData, borderColor: "#22c55e", backgroundColor: "rgba(34, 197, 94, 0.1)", fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: "#22c55e" },
                ],
            },
            options: {
                ..._chartDefaults(),
                plugins: { ..._chartDefaults().plugins, legend: { labels: { color: "#9ca3af" } } },
                scales: {
                    x: { ticks: { color: "#6b7280" }, grid: { color: "rgba(255,255,255,0.04)" } },
                    y: { ticks: { color: "#6b7280" }, grid: { color: "rgba(255,255,255,0.04)" } },
                },
            },
        });

    } catch (e) {
        console.error("Failed to load stats:", e);
        loading.hidden = true;
        empty.hidden = false;
    }
}

// --- Tabbed chart cards ---
document.querySelectorAll(".stats-tab-bar").forEach(bar => {
    bar.querySelectorAll(".stats-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            const card = bar.closest(".stats-tabbed-card");
            card.querySelectorAll(".stats-tab").forEach(t => t.classList.remove("active"));
            card.querySelectorAll(".stats-tab-panel").forEach(p => p.classList.remove("active"));
            tab.classList.add("active");
            card.querySelector(`#${tab.dataset.tab}`).classList.add("active");
        });
    });
});
