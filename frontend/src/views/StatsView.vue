<template>
  <section>
    <div class="page-header">
      <h1>Statistics</h1>
    </div>

    <div class="loading-state" v-if="loading">
      <div class="spinner"></div>
      <p>Loading statistics...</p>
    </div>

    <div class="empty-state" v-if="empty && !loading">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>
      <h3>No data</h3>
      <p>Add some cards to your collection to see statistics</p>
    </div>

    <div v-show="!loading && !empty">
      <!-- KPIs -->
      <div class="stats-overview-grid">
        <div class="stats-kpi-card"><div class="kpi-value">{{ kpi.totalValue }}</div><div class="kpi-label">Total Value</div></div>
        <div class="stats-kpi-card"><div class="kpi-value">{{ kpi.unique }}</div><div class="kpi-label">Unique Entries</div></div>
        <div class="stats-kpi-card"><div class="kpi-value">{{ kpi.copies }}</div><div class="kpi-label">Total Copies</div></div>
        <div class="stats-kpi-card"><div class="kpi-value">{{ kpi.distinct }}</div><div class="kpi-label">Distinct Cards</div></div>
        <div class="stats-kpi-card"><div class="kpi-value">{{ kpi.avgValue }}</div><div class="kpi-label">Avg Card Value</div></div>
        <div class="stats-kpi-card"><div class="kpi-value">{{ kpi.priced }}</div><div class="kpi-label">Priced / Unpriced</div></div>
      </div>

      <!-- Top Valuable -->
      <div class="stats-section-card">
        <h3>Most Valuable Cards</h3>
        <div class="top-valuable-list">
          <div v-for="(c, i) in topValuable" :key="i" class="top-valuable-item">
            <span class="tv-rank">#{{ i + 1 }}</span>
            <img class="tv-img" :src="cardImgUrl(c.image_url)" :alt="c.name" loading="lazy">
            <div class="tv-info">
              <div class="tv-name">{{ c.name }}</div>
              <div class="tv-meta">{{ c.set_code || '' }} &middot; {{ c.rarity }}</div>
            </div>
            <div class="tv-price-col">
              <div class="tv-price">{{ c.price.toFixed(2) }}&euro;</div>
              <div v-if="c.quantity > 1" class="tv-qty">x{{ c.quantity }} = {{ c.total_value.toFixed(2) }}&euro;</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Doughnut Charts -->
      <div class="stats-charts-grid">
        <div v-for="chart in doughnutCharts" :key="chart.id" class="stats-section-card">
          <h3>{{ chart.title }}</h3>
          <div class="chart-container"><canvas :ref="el => canvasRefs[chart.id] = el"></canvas></div>
        </div>
      </div>

      <!-- Wide Charts -->
      <div class="stats-charts-grid stats-charts-wide">
        <!-- Tabbed value by rarity -->
        <div class="stats-section-card stats-tabbed-card">
          <div class="stats-tab-bar">
            <button class="stats-tab" :class="{ active: activeRarityTab === 'value' }" @click="activeRarityTab = 'value'">Value by Rarity</button>
            <button class="stats-tab" :class="{ active: activeRarityTab === 'avg' }" @click="activeRarityTab = 'avg'">Avg Value by Rarity</button>
          </div>
          <div class="stats-tab-panel" :class="{ active: activeRarityTab === 'value' }">
            <div class="chart-container chart-wide"><canvas :ref="el => canvasRefs['chart-value-rarity'] = el"></canvas></div>
          </div>
          <div class="stats-tab-panel" :class="{ active: activeRarityTab === 'avg' }">
            <div class="chart-container chart-wide"><canvas :ref="el => canvasRefs['chart-avg-rarity'] = el"></canvas></div>
          </div>
        </div>
        <!-- Tabbed top sets -->
        <div class="stats-section-card stats-tabbed-card">
          <div class="stats-tab-bar">
            <button class="stats-tab" :class="{ active: activeSetsTab === 'count' }" @click="activeSetsTab = 'count'">Top Sets (Count)</button>
            <button class="stats-tab" :class="{ active: activeSetsTab === 'value' }" @click="activeSetsTab = 'value'">Top Sets (Value)</button>
          </div>
          <div class="stats-tab-panel" :class="{ active: activeSetsTab === 'count' }">
            <div class="chart-container chart-wide"><canvas :ref="el => canvasRefs['chart-sets'] = el"></canvas></div>
          </div>
          <div class="stats-tab-panel" :class="{ active: activeSetsTab === 'value' }">
            <div class="chart-container chart-wide"><canvas :ref="el => canvasRefs['chart-sets-value'] = el"></canvas></div>
          </div>
        </div>
        <div v-for="chart in wideCharts" :key="chart.id" class="stats-section-card">
          <h3>{{ chart.title }}</h3>
          <div class="chart-container chart-wide"><canvas :ref="el => canvasRefs[chart.id] = el"></canvas></div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { Chart, registerables } from 'chart.js'
import { cardImgUrl } from '../utils/images.js'
import api from '../api.js'

Chart.register(...registerables)

const loading = ref(true)
const empty = ref(false)
const activeRarityTab = ref('value')
const activeSetsTab = ref('count')
const kpi = reactive({ totalValue: '--', unique: '--', copies: '--', distinct: '--', avgValue: '--', priced: '--' })
const topValuable = ref([])
const canvasRefs = reactive({})
const charts = {}

const CHART_COLORS = ['#7c5cfc','#22c55e','#ef4444','#3b82f6','#eab308','#f97316','#06b6d4','#ec4899','#8b5cf6','#14b8a6','#f43f5e','#a855f7','#0ea5e9','#84cc16','#d946ef','#fbbf24','#6366f1','#10b981','#e11d48','#059669']
const ATTR_COLORS = { DARK:'#9333ea',LIGHT:'#fbbf24',FIRE:'#ef4444',WATER:'#3b82f6',EARTH:'#a16207',WIND:'#22c55e',DIVINE:'#f59e0b' }
const COND_COLORS = { 'Mint':'#00bcd4','Near Mint':'#4caf50','Excellent':'#8bc34a','Good':'#fdd835','Light Played':'#ff9800','Played':'#ff5722','Poor':'#f44336' }

const doughnutCharts = [
  { id: 'chart-rarity', title: 'By Rarity' },
  { id: 'chart-type', title: 'By Card Type' },
  { id: 'chart-condition', title: 'By Condition' },
  { id: 'chart-lang', title: 'By Language' },
  { id: 'chart-attribute', title: 'By Attribute' },
  { id: 'chart-race', title: 'By Monster Race' }
]

const wideCharts = [
  { id: 'chart-value-lang', title: 'Value by Language' },
  { id: 'chart-price-dist', title: 'Price Distribution' },
  { id: 'chart-level', title: 'Monster Level Distribution' },
  { id: 'chart-archetypes', title: 'Top Archetypes' },
  { id: 'chart-atk-def', title: 'ATK / DEF Distribution' },
  { id: 'chart-growth', title: 'Collection Growth' }
]

function chartDefaults() {
  return { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#9ca3af', font: { family: "'Inter', sans-serif", size: 11 } } } } }
}

function createDoughnut(id, labels, data, colors) {
  const ctx = canvasRefs[id]
  if (!ctx) return
  charts[id] = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: colors || labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]), borderColor: 'rgba(0,0,0,0.3)', borderWidth: 1 }] },
    options: { ...chartDefaults(), cutout: '55%', plugins: { ...chartDefaults().plugins, legend: { position: 'right', labels: { color: '#9ca3af', font: { family: "'Inter', sans-serif", size: 11 }, padding: 8 } } } }
  })
}

function createBar(id, labels, data, color, label) {
  const ctx = canvasRefs[id]
  if (!ctx) return
  charts[id] = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ label: label || '', data, backgroundColor: typeof color === 'string' ? color : labels.map((_, i) => (color || CHART_COLORS)[i % (color || CHART_COLORS).length]), borderRadius: 4 }] },
    options: { ...chartDefaults(), indexAxis: 'x', plugins: { ...chartDefaults().plugins, legend: { display: false } }, scales: { x: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } }, y: { ticks: { color: '#6b7280' }, grid: { color: 'rgba(255,255,255,0.04)' } } } }
  })
}

function createHorizontalBar(id, labels, data, colors) {
  const ctx = canvasRefs[id]
  if (!ctx) return
  const barHeight = 28, minHeight = 200
  const neededHeight = Math.max(minHeight, labels.length * barHeight + 40)
  ctx.parentElement.style.height = neededHeight + 'px'
  charts[id] = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ data, backgroundColor: colors || labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]), borderRadius: 4 }] },
    options: { ...chartDefaults(), indexAxis: 'y', plugins: { ...chartDefaults().plugins, legend: { display: false } }, scales: { x: { ticks: { color: '#6b7280' }, grid: { color: 'rgba(255,255,255,0.04)' } }, y: { ticks: { color: '#9ca3af', font: { size: 11 }, autoSkip: false }, grid: { display: false } } } }
  })
}

function destroyCharts() {
  Object.values(charts).forEach(c => c.destroy())
  Object.keys(charts).forEach(k => delete charts[k])
}

onMounted(async () => {
  try {
    const stats = await api.getStats()
    loading.value = false
    if (stats.empty) { empty.value = true; return }

    const ov = stats.overview
    kpi.totalValue = `${ov.total_value.toFixed(2)}\u20AC`
    kpi.unique = ov.total_unique.toLocaleString()
    kpi.copies = ov.total_copies.toLocaleString()
    kpi.distinct = ov.distinct_cards.toLocaleString()
    kpi.avgValue = `${ov.avg_card_value.toFixed(2)}\u20AC`
    kpi.priced = `${ov.priced_count} / ${ov.unpriced_count}`
    topValuable.value = stats.top_valuable

    // Wait for DOM update
    await new Promise(r => setTimeout(r, 50))

    const dist = stats.distributions
    createDoughnut('chart-rarity', Object.keys(dist.rarity), Object.values(dist.rarity))
    createDoughnut('chart-type', Object.keys(dist.type), Object.values(dist.type))
    createDoughnut('chart-condition', Object.keys(dist.condition), Object.values(dist.condition), Object.keys(dist.condition).map(k => COND_COLORS[k] || CHART_COLORS[0]))
    createDoughnut('chart-lang', Object.keys(dist.language), Object.values(dist.language))
    createDoughnut('chart-attribute', Object.keys(dist.attribute), Object.values(dist.attribute), Object.keys(dist.attribute).map(k => ATTR_COLORS[k] || CHART_COLORS[0]))
    createDoughnut('chart-race', Object.keys(dist.race), Object.values(dist.race))

    const rarityLabels = Object.keys(stats.value_by_rarity).map(k => `${k} (${stats.count_by_rarity[k] || 0})`)
    createHorizontalBar('chart-value-rarity', rarityLabels, Object.values(stats.value_by_rarity))
    const avgLabels = Object.keys(stats.avg_by_rarity).map(k => `${k} (${stats.count_by_rarity[k] || 0})`)
    createHorizontalBar('chart-avg-rarity', avgLabels, Object.values(stats.avg_by_rarity))
    createHorizontalBar('chart-value-lang', Object.keys(stats.value_by_lang), Object.values(stats.value_by_lang))
    createBar('chart-price-dist', Object.keys(stats.price_distribution), Object.values(stats.price_distribution), '#7c5cfc')
    createBar('chart-level', Object.keys(dist.level).map(l => `Lv ${l}`), Object.values(dist.level), '#3b82f6')
    createHorizontalBar('chart-sets', Object.keys(dist.set), Object.values(dist.set))
    const setValueLabels = Object.keys(stats.value_by_set).map(k => `${k} (${stats.count_by_set[k] || 0})`)
    createHorizontalBar('chart-sets-value', setValueLabels, Object.values(stats.value_by_set))
    createHorizontalBar('chart-archetypes', Object.keys(dist.archetype), Object.values(dist.archetype))

    // Scatter
    const scatterCtx = canvasRefs['chart-atk-def']
    if (scatterCtx) {
      charts['chart-atk-def'] = new Chart(scatterCtx, {
        type: 'scatter',
        data: { datasets: [{ label: 'Monsters', data: stats.atk_def_scatter.map(m => ({ x: m.atk, y: m.def, name: m.name })), backgroundColor: 'rgba(124,92,252,0.5)', borderColor: '#7c5cfc', pointRadius: 3, pointHoverRadius: 6 }] },
        options: { ...chartDefaults(), plugins: { ...chartDefaults().plugins, legend: { display: false }, tooltip: { callbacks: { label: ctx => `${ctx.raw.name}: ATK ${ctx.raw.x} / DEF ${ctx.raw.y}` } } }, scales: { x: { title: { display: true, text: 'ATK', color: '#6b7280' }, ticks: { color: '#6b7280' }, grid: { color: 'rgba(255,255,255,0.04)' } }, y: { title: { display: true, text: 'DEF', color: '#6b7280' }, ticks: { color: '#6b7280' }, grid: { color: 'rgba(255,255,255,0.04)' } } } }
      })
    }

    // Growth
    const months = Object.keys(stats.growth_by_month)
    const growthData = Object.values(stats.growth_by_month)
    const cumulative = []; growthData.reduce((acc, val, i) => { cumulative[i] = acc + val; return cumulative[i] }, 0)
    const growthCtx = canvasRefs['chart-growth']
    if (growthCtx) {
      charts['chart-growth'] = new Chart(growthCtx, {
        type: 'line',
        data: { labels: months, datasets: [
          { label: 'Cumulative', data: cumulative, borderColor: '#7c5cfc', backgroundColor: 'rgba(124,92,252,0.1)', fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: '#7c5cfc' },
          { label: 'Added', data: growthData, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.1)', fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: '#22c55e' }
        ] },
        options: { ...chartDefaults(), plugins: { ...chartDefaults().plugins, legend: { labels: { color: '#9ca3af' } } }, scales: { x: { ticks: { color: '#6b7280' }, grid: { color: 'rgba(255,255,255,0.04)' } }, y: { ticks: { color: '#6b7280' }, grid: { color: 'rgba(255,255,255,0.04)' } } } }
      })
    }
  } catch (e) {
    console.error('Failed to load stats:', e)
    loading.value = false
    empty.value = true
  }
})

onUnmounted(destroyCharts)
</script>
