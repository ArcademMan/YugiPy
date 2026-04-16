<template>
  <div class="modal" :hidden="!visible">
    <div class="modal-backdrop" @click="$emit('close')"></div>
    <div class="modal-content modal-large">
      <button class="modal-close" @click="$emit('close')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <h2>Book Settings</h2>
      <div class="book-settings-body">
        <div class="book-settings-col">
          <div class="form-group">
            <label>Group by</label>
            <select v-model="prefs.groupBy" @change="emitChange">
              <option value="set">Set</option>
              <option value="archetype">Archetype</option>
              <option value="type">Type</option>
              <option value="none">None</option>
            </select>
          </div>
          <div class="form-group">
            <label>Sort rules <small>(drag to reorder)</small></label>
            <div class="sort-rules-list">
              <div
                v-for="(rule, idx) in sortRules"
                :key="idx"
                class="sort-rule-row"
                draggable="true"
                @dragstart="onDragStart($event, idx)"
                @dragend="onDragEnd"
                @dragover.prevent
                @drop="onDrop($event, idx)"
              >
                <span class="sort-rule-grip">&equiv;</span>
                <select :value="rule" @change="onRuleChange(idx, $event.target.value)" class="sort-rule-select">
                  <option v-for="opt in SORT_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
                <button type="button" class="sort-rule-remove" @click="removeRule(idx)">&times;</button>
              </div>
            </div>
            <button type="button" class="btn-add-rule" @click="addRule">+ Add rule</button>
          </div>
        </div>
        <div class="book-settings-col">
          <div class="form-group">
            <label>Cards per page</label>
            <select v-model="prefs.gridSize" @change="emitChange">
              <option value="3x3">3&times;3 (9)</option>
              <option value="4x3">4&times;3 (12)</option>
              <option value="4x4">4&times;4 (16)</option>
              <option value="5x4">5&times;4 (20)</option>
            </select>
          </div>
          <div class="form-group">
            <label>Max copies per card</label>
            <select v-model="prefs.maxCopies" @change="emitChange">
              <option value="0">All</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
              <option value="4">4</option>
            </select>
          </div>
          <div class="form-group">
            <label>Count copies by</label>
            <select v-model="prefs.copiesMode" @change="emitChange">
              <option value="entry">Exact card (set + rarity + lang)</option>
              <option value="name">Card name</option>
            </select>
          </div>
          <div class="form-group">
            <label>Language</label>
            <MultiSelect
              :options="LANG_OPTIONS"
              v-model="prefs.filterLangs"
              placeholder="All"
              @update:modelValue="emitChange"
            />
          </div>
          <div class="form-group">
            <label>Condition</label>
            <MultiSelect
              :options="CONDITION_OPTIONS"
              v-model="prefs.filterConditions"
              placeholder="All"
              @update:modelValue="emitChange"
            />
          </div>
          <div class="form-group">
            <label>Archetype</label>
            <button type="button" class="multi-select-trigger" @click="archPickerVisible = true">
              <span class="multi-select-label">{{ archButtonLabel }}</span>
              <span class="multi-select-arrow">&#9662;</span>
            </button>
          </div>
          <ArchetypePickerModal
            :visible="archPickerVisible"
            :archetypes="availableArchetypes"
            :availability="archetypeAvailability"
            v-model="prefs.filterArchetypes"
            @update:modelValue="onArchetypesChange"
            @close="archPickerVisible = false"
          />
          <div class="form-group">
            <label>Set</label>
            <MultiSelect
              :options="setOptions"
              v-model="prefs.filterSets"
              placeholder="All sets"
              @update:modelValue="emitChange"
            />
          </div>
          <div class="form-group">
            <label>Min price (&euro;)</label>
            <input type="number" v-model.number="prefs.minPrice" min="0" step="0.5" style="width:100%" @input="emitChange">
          </div>
          <label class="book-checkbox-label">
            <input type="checkbox" v-model="prefs.newPage" @change="emitChange">
            Separate groups on new page
          </label>
          <label class="book-checkbox-label">
            <input type="checkbox" v-model="prefs.showPrices" @change="emitChange">
            Show prices on cards
          </label>
          <label class="book-checkbox-label">
            <input type="checkbox" v-model="prefs.groupDuplicates" @change="emitChange">
            Keep same-name cards together
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { LANG_OPTIONS, CONDITION_OPTIONS } from '../utils/constants.js'
import MultiSelect from './MultiSelect.vue'
import ArchetypePickerModal from './ArchetypePickerModal.vue'

const SORT_OPTIONS = [
  { value: 'rarity_desc', label: 'Rarity \u2193' },
  { value: 'rarity_asc', label: 'Rarity \u2191' },
  { value: 'name_asc', label: 'Name A\u2192Z' },
  { value: 'name_desc', label: 'Name Z\u2192A' },
  { value: 'type_asc', label: 'Type \u2191' },
  { value: 'type_desc', label: 'Type \u2193' },
  { value: 'type_creature_asc', label: 'Creature type \u2191' },
  { value: 'type_creature_desc', label: 'Creature type \u2193' },
  { value: 'level_desc', label: 'Level \u2193' },
  { value: 'level_asc', label: 'Level \u2191' },
  { value: 'set_code_asc', label: 'Set code A\u2192Z' },
  { value: 'set_code_desc', label: 'Set code Z\u2192A' },
  { value: 'price_desc', label: 'Price \u2193' },
  { value: 'price_asc', label: 'Price \u2191' },
  { value: 'archetype_asc', label: 'Archetype A\u2192Z' },
  { value: 'archetype_desc', label: 'Archetype Z\u2192A' }
]

const props = defineProps({
  visible: { type: Boolean, default: false },
  availableSets: { type: Array, default: () => [] },
  availableArchetypes: { type: Array, default: () => [] },
  archetypeAvailability: { type: Object, default: () => ({}) },
  initialPrefs: { type: Object, default: null },
  initialSortRules: { type: Array, default: null }
})

const emit = defineEmits(['change', 'close'])

const sortRules = reactive(props.initialSortRules || ['rarity_desc'])

const setOptions = computed(() =>
  props.availableSets.map(s => ({ value: s, label: s }))
)

const archPickerVisible = ref(false)

const archButtonLabel = computed(() => {
  const n = prefs.filterArchetypes?.length || 0
  if (n === 0) return 'All archetypes'
  if (n <= 2) return prefs.filterArchetypes.join(', ')
  return `${n} archetypes selected`
})

function onArchetypesChange(val) {
  prefs.filterArchetypes = val
  emitChange()
}

// Migrate old single-value prefs to arrays
function migratePrefs(saved) {
  if (!saved) return {}
  const out = { ...saved }
  if (typeof out.filterLang === 'string') {
    out.filterLangs = out.filterLang ? [out.filterLang] : []
    delete out.filterLang
  }
  if (typeof out.filterCondition === 'string') {
    out.filterConditions = out.filterCondition ? [out.filterCondition] : []
    delete out.filterCondition
  }
  if (typeof out.filterSet === 'string') {
    out.filterSets = out.filterSet ? [out.filterSet] : []
    delete out.filterSet
  }
  return out
}

const prefs = reactive({
  groupBy: 'set',
  gridSize: '3x3',
  maxCopies: '0',
  copiesMode: 'entry',
  filterLangs: [],
  filterConditions: [],
  filterArchetypes: [],
  filterSets: [],
  minPrice: 0,
  newPage: true,
  showPrices: false,
  groupDuplicates: false,
  ...migratePrefs(props.initialPrefs)
})

let dragIdx = -1
function onDragStart(e, idx) { dragIdx = idx; e.dataTransfer.effectAllowed = 'move' }
function onDragEnd() { dragIdx = -1 }
function onDrop(e, toIdx) {
  e.preventDefault()
  if (dragIdx === toIdx || dragIdx < 0) return
  const [moved] = sortRules.splice(dragIdx, 1)
  sortRules.splice(toIdx, 0, moved)
  dragIdx = -1
  emitChange()
}
function onRuleChange(idx, val) { sortRules[idx] = val; emitChange() }
function removeRule(idx) {
  sortRules.splice(idx, 1)
  if (sortRules.length === 0) sortRules.push('rarity_desc')
  emitChange()
}
function addRule() {
  const used = new Set(sortRules)
  const next = SORT_OPTIONS.find(o => !used.has(o.value))
  sortRules.push(next ? next.value : 'rarity_desc')
  emitChange()
}

function emitChange() {
  emit('change', { prefs: { ...prefs }, sortRules: [...sortRules] })
}

defineExpose({ prefs, sortRules })
</script>
