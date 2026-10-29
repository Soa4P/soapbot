<script setup lang="ts">
import { computed } from 'vue'

import { t } from '@/i18n'

/**
 * Horizontal bars, one row per category.
 *
 * Horizontal, not vertical, because the categories here are stage names and halt
 * reasons — Chinese text, sometimes six characters. Vertical bars would need rotated
 * labels, and rotated labels are the single most common reason a chart is unreadable.
 *
 * Each row is a real `<button>`? No: these bars are not actions. They are a list, and
 * they are marked up as one so a screen reader reads the row as one sentence
 * rather than announcing fifteen buttons.
 */
interface Item {
  label: string
  value: number
  tone?: 'brand' | 'ok' | 'warn' | 'danger'
}

const props = withDefaults(
  defineProps<{
    items: Item[]
    title: string
    unit?: string
    /** Shown when every value is zero, so the chart does not look broken. */
    emptyText?: string
  }>(),
  { unit: '', emptyText: '' },
)

const max = computed(() => {
  const values = props.items.map((i) => i.value).filter((v) => Number.isFinite(v))
  return values.length ? Math.max(...values) || 1 : 1
})

function width(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0%'
  // Floor at 2% so a non-zero value is visibly non-zero; a 1px bar reads as missing.
  return `${Math.max(2, (value / max.value) * 100)}%`
}

function toneClass(tone?: string): string {
  return tone ? `bar__fill bar__fill--${tone}` : 'bar__fill'
}
</script>

<template>
  <figure class="bars">
    <figcaption class="bars__cap">{{ title }}</figcaption>

    <p v-if="!items.length" class="empty">{{ emptyText || t('chart.noData') }}</p>

    <ul v-else class="bars__list">
      <li v-for="item in items" :key="item.label" class="bar">
        <span class="bar__label">{{ item.label }}</span>
        <span class="bar__track">
          <span :class="toneClass(item.tone)" :style="{ width: width(item.value) }" />
        </span>
        <span class="bar__value mono">
          {{ Number.isFinite(item.value) ? Math.round(item.value * 10) / 10 : '—' }}{{ unit }}
        </span>
      </li>
    </ul>

    <details v-if="items.length" class="bars__data">
      <summary>{{ t('chart.viewAsTable') }}</summary>
      <table class="data">
        <caption class="visually-hidden">{{ title }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('chart.item') }}</th>
            <th scope="col">{{ t('chart.value') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="`row-${item.label}`">
            <th scope="row">{{ item.label }}</th>
            <td class="num">{{ item.value }}{{ unit }}</td>
          </tr>
        </tbody>
      </table>
    </details>
  </figure>
</template>

<style scoped>
.bars {
  margin: 0;
  display: grid;
  gap: 8px;
}

.bars__cap {
  font-family: var(--serif);
  font-size: 14px;
  color: var(--ink);
}

.bars__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 6px;
}

.bar {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr) 64px;
  align-items: center;
  gap: 10px;
}

.bar__label {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bar__track {
  height: 8px;
  border-radius: 4px;
  background: var(--surface-3);
  overflow: hidden;
}

.bar__fill {
  display: block;
  height: 100%;
  border-radius: 4px;
  background: var(--chart-1);
  transition: width 240ms cubic-bezier(0.22, 0.61, 0.36, 1);
}

.bar__fill--ok {
  background: var(--chart-2);
}
.bar__fill--warn {
  background: var(--chart-3);
}
.bar__fill--danger {
  background: var(--danger);
}

.bar__value {
  font-size: 11px;
  color: var(--ink);
  text-align: right;
}

.bars__data summary {
  cursor: pointer;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--brand);
  width: fit-content;
}

.bars__data summary:hover {
  text-decoration: underline;
}
</style>
