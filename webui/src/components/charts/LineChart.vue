<script setup lang="ts">
import { computed, ref } from 'vue'

/**
 * Multi-series line chart with axes, drawn as inline SVG.
 *
 * Why not a charting library
 * --------------------------
 * `scripts/check_deps.py` treats the dependency list as an audit surface, and four
 * unused packages were removed from it recently. Adding a charting library for two
 * line charts and one bar chart would be the same mistake in the other direction.
 *
 * More importantly, canvas-based libraries (and most chart libraries, which render to
 * canvas) produce an opaque bitmap: a screen reader sees "canvas", and the keyboard
 * cannot reach a data point. WCAG AA requires the data to be available — so a canvas
 * chart needs a parallel DOM table anyway, which is most of the work of drawing it in
 * SVG. SVG gives `role="img"` + `<title>`, focusable points, and real text for free.
 *
 * The trade-off is stated honestly: this handles tens to low hundreds of points well
 * and would not replace a real charting library for 100k-point time series.
 */
interface Series {
  key: string
  label: string
  values: (number | null)[]
  tone?: 'brand' | 'ok' | 'warn' | 'danger' | 'muted'
}

const props = withDefaults(
  defineProps<{
    series: Series[]
    /** X labels, one per point. Index-aligned with `values`. */
    labels: string[]
    title: string
    yLabel?: string
    height?: number
    /** Formats a value for the tooltip and the accessible table. */
    format?: (value: number) => string
  }>(),
  { yLabel: '', height: 220, format: (v: number) => String(v) },
)

const W = 760
const H = computed(() => props.height)
const PAD_L = 52
const PAD_R = 14
const PAD_T = 12
const PAD_B = 30

const hover = ref<number | null>(null)

const palette: Record<string, string> = {
  brand: 'var(--chart-1)',
  ok: 'var(--chart-2)',
  warn: 'var(--chart-3)',
  danger: 'var(--danger)',
  muted: 'var(--ink-3)',
}

const allValues = computed(() => {
  const out: number[] = []
  for (const s of props.series) {
    for (const v of s.values) if (typeof v === 'number' && Number.isFinite(v)) out.push(v)
  }
  return out
})

const maxValue = computed(() => {
  const values = allValues.value
  if (!values.length) return 1
  const max = Math.max(...values)
  // A non-zero axis: "0 to 0" would draw every series as a flat line at the top.
  return max <= 0 ? 1 : max * 1.1
})

const pointCount = computed(() =>
  Math.max(1, ...props.series.map((s) => s.values.length), props.labels.length),
)

function x(index: number): number {
  const count = Math.max(1, pointCount.value - 1)
  return PAD_L + (index / count) * (W - PAD_L - PAD_R)
}

function y(value: number): number {
  const usable = H.value - PAD_T - PAD_B
  return PAD_T + (1 - value / maxValue.value) * usable
}

const paths = computed(() =>
  props.series.map((s) => {
    let d = ''
    let started = false
    s.values.forEach((value, index) => {
      if (typeof value !== 'number' || !Number.isFinite(value)) {
        // A gap is a gap: breaking the path is the honest rendering of "no sample".
        // Drawing through it would invent data between two points.
        started = false
        return
      }
      d += `${started ? 'L' : 'M'}${x(index).toFixed(1)},${y(value).toFixed(1)} `
      started = true
    })
    return { key: s.key, d: d.trim(), stroke: palette[s.tone ?? 'brand'] ?? palette.brand }
  }),
)

const yTicks = computed(() => {
  const ticks: { value: number; y: number }[] = []
  for (let i = 0; i <= 4; i += 1) {
    const value = (maxValue.value / 4) * i
    ticks.push({ value, y: y(value) })
  }
  return ticks
})

/** Only every nth label is drawn, so the axis does not become a grey smear. */
const xTicks = computed(() => {
  const count = pointCount.value
  const step = Math.max(1, Math.ceil(count / 7))
  const out: { label: string; x: number }[] = []
  for (let i = 0; i < count; i += step) {
    const label = props.labels[i]
    if (label) out.push({ label, x: x(i) })
  }
  return out
})

function onMove(event: MouseEvent): void {
  const target = event.currentTarget as SVGSVGElement
  const rect = target.getBoundingClientRect()
  const ratio = (event.clientX - rect.left) / rect.width
  const approx = Math.round(((ratio * W - PAD_L) / (W - PAD_L - PAD_R)) * (pointCount.value - 1))
  hover.value = Math.min(pointCount.value - 1, Math.max(0, approx))
}

const readout = computed(() => {
  if (hover.value === null) return null
  const index = hover.value
  return {
    label: props.labels[index] ?? `#${index + 1}`,
    entries: props.series.map((s) => ({
      label: s.label,
      value: s.values[index],
      stroke: palette[s.tone ?? 'brand'] ?? palette.brand,
    })),
  }
})
</script>

<template>
  <figure class="chart">
    <figcaption class="chart__cap">
      <span>{{ title }}</span>
      <span v-if="yLabel" class="chart__unit">{{ yLabel }}</span>
    </figcaption>

    <div class="chart__plot">
      <svg
        :viewBox="`0 0 ${W} ${H}`"
        class="chart__svg"
        role="img"
        :aria-label="`${title}。${series.map((s) => s.label).join('、')}。数据点在下方表格中可读。`"
        @mousemove="onMove"
        @mouseleave="hover = null"
      >
        <title>{{ title }}</title>

        <g class="chart__grid">
          <line
            v-for="tick in yTicks"
            :key="`g${tick.value}`"
            :x1="PAD_L"
            :y1="tick.y"
            :x2="W - PAD_R"
            :y2="tick.y"
          />
        </g>

        <g class="chart__axis">
          <text
            v-for="tick in yTicks"
            :key="`t${tick.value}`"
            :x="PAD_L - 8"
            :y="tick.y + 3.5"
            text-anchor="end"
          >
            {{ format(tick.value) }}
          </text>
          <text v-for="tick in xTicks" :key="`x${tick.x}`" :x="tick.x" :y="H - 10" text-anchor="middle">
            {{ tick.label }}
          </text>
        </g>

        <g>
          <path
            v-for="line in paths"
            :key="line.key"
            :d="line.d"
            fill="none"
            :stroke="line.stroke"
            stroke-width="1.8"
            stroke-linejoin="round"
            stroke-linecap="round"
          />
        </g>

        <line
          v-if="hover !== null"
          :x1="x(hover)"
          :y1="PAD_T"
          :x2="x(hover)"
          :y2="H - PAD_B"
          class="chart__cursor"
        />
      </svg>

      <div v-if="readout" class="chart__tip" role="status">
        <span class="chart__tip-time mono">{{ readout.label }}</span>
        <span v-for="entry in readout.entries" :key="entry.label" class="chart__tip-row">
          <i class="chart__dot" :style="{ background: entry.stroke }" />
          <span class="chart__tip-label">{{ entry.label }}</span>
          <span class="mono">
            {{ typeof entry.value === 'number' ? format(entry.value) : '—' }}
          </span>
        </span>
      </div>
    </div>

    <ul class="chart__legend">
      <li v-for="s in series" :key="s.key">
        <i class="chart__dot" :style="{ background: palette[s.tone ?? 'brand'] }" />
        {{ s.label }}
      </li>
    </ul>

    <!--
      The same data as a table, collapsed by default. This is what makes the chart
      WCAG-compliant: a screen-reader user gets exact values, and a sighted user who
      needs a precise number can open it instead of estimating from pixels.
    -->
    <details class="chart__data">
      <summary>以表格查看数值</summary>
      <div class="scroll" style="max-height: 240px">
        <table class="data">
          <caption class="visually-hidden">{{ title }} 数据</caption>
          <thead>
            <tr>
              <th scope="col">时间</th>
              <th v-for="s in series" :key="s.key" scope="col">{{ s.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(label, index) in labels" :key="`${label}-${index}`">
              <th scope="row">{{ label }}</th>
              <td v-for="s in series" :key="s.key" class="num">
                {{ typeof s.values[index] === 'number' ? format(s.values[index] as number) : '—' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </figure>
</template>

<style scoped>
.chart {
  margin: 0;
  display: grid;
  gap: 8px;
}

.chart__cap {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-family: var(--serif);
  font-size: 14px;
  color: var(--ink);
}

.chart__unit {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--ink-3);
}

.chart__plot {
  position: relative;
}

.chart__svg {
  width: 100%;
  display: block;
}

.chart__grid line {
  stroke: var(--chart-grid);
  stroke-width: 1;
}

.chart__axis text {
  font-family: var(--mono);
  font-size: 10px;
  fill: var(--ink-3);
}

.chart__cursor {
  stroke: var(--border-strong);
  stroke-width: 1;
  stroke-dasharray: 3 3;
}

.chart__tip {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 132px;
  display: grid;
  gap: 3px;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  box-shadow: var(--shadow);
  font-size: 11px;
  pointer-events: none;
}

.chart__tip-time {
  font-size: 10px;
  color: var(--ink-3);
}

.chart__tip-row {
  display: grid;
  grid-template-columns: 8px 1fr auto;
  align-items: center;
  gap: 6px;
}

.chart__tip-label {
  color: var(--ink-2);
}

.chart__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-2);
}

.chart__legend li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.chart__dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex: none;
}

.chart__data summary {
  cursor: pointer;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--brand);
  width: fit-content;
}

.chart__data summary:hover {
  text-decoration: underline;
}
</style>
