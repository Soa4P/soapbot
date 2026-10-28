<script setup lang="ts">
import { computed } from 'vue'

/**
 * A trend line with no axes, for embedding inside a readout.
 *
 * Deliberately not a chart library: the whole point of this component is to be 40
 * lines and render in one paint. A dependency would need to ship its own layout
 * engine for what is a single polyline.
 *
 * The `label` is required, not optional. A sparkline with no accessible name is
 * announced as "graphic", which tells a screen-reader user nothing; and its shape is
 * the only information it carries, so the label has to state the trend in words.
 */
const props = withDefaults(
  defineProps<{
    values: number[]
    label: string
    /** Rendered next to the label; keep it to the same unit as the values. */
    suffix?: string
    height?: number
    tone?: 'brand' | 'ok' | 'warn' | 'danger'
  }>(),
  { suffix: '', height: 36, tone: 'brand' },
)

const width = 160
const pad = 2

const points = computed(() => {
  const values = props.values.filter((v) => Number.isFinite(v))
  if (values.length < 2) return ''
  const min = Math.min(...values)
  const max = Math.max(...values)
  // A flat series must sit in the middle, not on the floor: min === max would divide
  // by zero, and pinning it to the baseline reads as "dropped to nothing".
  const span = max - min || 1
  const stepX = (width - pad * 2) / (values.length - 1)
  return values
    .map((value, index) => {
      const x = pad + index * stepX
      const y = max === min ? props.height / 2 : pad + (1 - (value - min) / span) * (props.height - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})

const stroke = computed(() => {
  switch (props.tone) {
    case 'ok':
      return 'var(--ok)'
    case 'warn':
      return 'var(--warn)'
    case 'danger':
      return 'var(--danger)'
    default:
      return 'var(--brand)'
  }
})

const latest = computed(() => {
  const values = props.values.filter((v) => Number.isFinite(v))
  return values.length ? values[values.length - 1] : null
})
</script>

<template>
  <div class="spark">
    <div class="spark__head">
      <span class="spark__label">{{ label }}</span>
      <span v-if="latest !== null" class="spark__value mono">
        {{ latest }}{{ suffix }}
      </span>
    </div>
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      :height="height"
      class="spark__svg"
      role="img"
      :aria-label="`${label}：最新 ${latest ?? '无数据'}${suffix}`"
      preserveAspectRatio="none"
    >
      <title>{{ label }}：最新 {{ latest ?? '无数据' }}{{ suffix }}</title>
      <polyline v-if="points" :points="points" fill="none" :stroke="stroke" stroke-width="1.5" />
      <line
        v-else
        :x1="pad"
        :y1="height / 2"
        :x2="width - pad"
        :y2="height / 2"
        stroke="var(--border-strong)"
        stroke-dasharray="3 3"
      />
    </svg>
  </div>
</template>

<style scoped>
.spark {
  display: grid;
  gap: 4px;
}

.spark__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.spark__label {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.spark__value {
  font-size: 12px;
  color: var(--ink);
}

.spark__svg {
  width: 100%;
  display: block;
  overflow: visible;
}
</style>
