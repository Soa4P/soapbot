<script setup lang="ts">
import { computed, ref } from 'vue'

import { t } from '@/i18n'

/**
 * The pipeline as a vertical chain, with each stage's measured share of one message.
 *
 * Why vertical and why not free-form
 * ----------------------------------
 * The order of these stages is the security model, not a layout choice: `sanitize`
 * before `injection_screen`, `safety` before `reply`. A horizontal flow diagram that
 * invites rearrangement would misrepresent it. A vertical list reads top-to-bottom,
 * which is the actual direction of travel, and cannot be misread as a graph you edit.
 *
 * The sandbox (below) exists because the question "why can't I move this?" deserves an
 * answer better than a disabled drag handle: drag a stage and the panel names the
 * specific invariant that breaks — "normalise before screening for injection; reversed,
 * zero-width characters defeat the keyword match"
 * — then resets. Nothing is sent to the server except a read-only check.
 */
interface Stage {
  name: string
  label: string
  order: number
}

interface Constraint {
  before: string
  after: string
  why: string
}

interface Timing {
  name: string
  elapsed_ms: number
}

const props = withDefaults(
  defineProps<{
    stages: Stage[]
    constraints?: Constraint[]
    /** Per-stage timing of the selected trace. Empty renders a topology-only view. */
    timings?: Timing[]
    /** Stage the message halted at, if it halted. */
    haltedAt?: string
  }>(),
  { constraints: () => [], timings: () => [], haltedAt: '' },
)

const totalMs = computed(() => props.timings.reduce((sum, t) => sum + t.elapsed_ms, 0))

const byName = computed(() => {
  const map = new Map<string, number>()
  for (const t of props.timings) map.set(t.name, t.elapsed_ms)
  return map
})

const slowest = computed(() => {
  if (!props.timings.length) return ''
  return props.timings.reduce((a, b) => (b.elapsed_ms > a.elapsed_ms ? b : a)).name
})

function ms(name: string): number | null {
  const value = byName.value.get(name)
  return typeof value === 'number' ? value : null
}

function share(name: string): number {
  const value = ms(name)
  if (!value || !totalMs.value) return 0
  return Math.min(100, (value / totalMs.value) * 100)
}

function fmt(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`
  if (value >= 10) return `${Math.round(value)} ms`
  return `${value.toFixed(1)} ms`
}

/* ------------------------------------------------------------------ sandbox */

const sandboxOpen = ref(false)
const sandboxOrder = ref<string[]>([])
const dragging = ref<string | null>(null)
const violations = ref<Constraint[]>([])

function openSandbox(): void {
  sandboxOrder.value = props.stages.map((s) => s.name)
  violations.value = []
  sandboxOpen.value = true
}

function closeSandbox(): void {
  sandboxOpen.value = false
  violations.value = []
  dragging.value = null
}

function onDragStart(name: string): void {
  dragging.value = name
}

function onDrop(target: string): void {
  const from = dragging.value
  dragging.value = null
  if (!from || from === target) return

  const next = [...sandboxOrder.value]
  const fromIndex = next.indexOf(from)
  const toIndex = next.indexOf(target)
  if (fromIndex < 0 || toIndex < 0) return
  next.splice(fromIndex, 1)
  next.splice(toIndex, 0, from)
  sandboxOrder.value = next
  evaluate(next)
}

function evaluate(order: string[]): void {
  // Evaluated locally against the same constraint list the server returns, so the
  // feedback is immediate. The server endpoint exists for the case where the client's
  // copy of the constraints is stale; this is a teaching tool, not a security control.
  const position = new Map(order.map((name, index) => [name, index]))
  violations.value = props.constraints.filter((c) => {
    const before = position.get(c.before)
    const after = position.get(c.after)
    if (before === undefined || after === undefined) return false
    return before > after
  })
}

function labelOf(name: string): string {
  return props.stages.find((s) => s.name === name)?.label ?? name
}

const sandboxStages = computed(() =>
  sandboxOrder.value.map((name) => props.stages.find((s) => s.name === name)).filter(Boolean) as Stage[],
)
</script>

<template>
  <div class="graph">
    <div class="graph__head">
      <div>
        <h2>{{ t('graph.title') }}</h2>
        <p class="hint" style="margin: 2px 0 0">
          {{ t('graph.subtitle', { n: stages.length }) }}
        </p>
      </div>
      <button class="btn ghost" type="button" @click="openSandbox">{{ t('graph.sandbox') }}</button>
    </div>

    <ol class="chain">
      <li
        v-for="stage in stages"
        :key="stage.name"
        class="node"
        :class="{
          'node--halted': stage.name === haltedAt,
          'node--slow': stage.name === slowest && totalMs > 0,
          'node--idle': !timings.length,
        }"
      >
        <span class="node__marker" aria-hidden="true">{{ stage.order + 1 }}</span>

        <div class="node__body">
          <div class="node__title">
            <span class="node__label">{{ stage.label }}</span>
            <code class="node__name mono">{{ stage.name }}</code>
            <span v-if="stage.name === haltedAt" class="pill bad"><i class="dot" />{{ t('graph.haltedHere') }}</span>
            <span v-else-if="ms(stage.name) === null && timings.length" class="tag">{{ t('graph.notRun') }}</span>
          </div>

          <div v-if="ms(stage.name) !== null" class="node__timing">
            <span class="node__bar">
              <span class="node__fill" :style="{ width: `${share(stage.name)}%` }" />
            </span>
            <span class="node__ms mono">{{ fmt(ms(stage.name) as number) }}</span>
          </div>
        </div>
      </li>
    </ol>

    <div v-if="totalMs > 0" class="graph__foot">
      <span class="mono">{{ t('graph.total', { value: fmt(totalMs) }) }}</span>
      <span class="faint">·</span>
      <span class="mono">{{ t('graph.slowest', { name: labelOf(slowest) }) }}</span>
    </div>

    <!-- Sandbox: modal on purpose. A drag experiment that stays open next to the real
         graph gets confused with it after thirty seconds. -->
    <Teleport to="body">
      <div v-if="sandboxOpen" class="overlay" @click.self="closeSandbox">
        <div class="dialog dialog--wide" role="dialog" aria-modal="true" aria-labelledby="sb-title">
          <div class="dialog__head">
            <div class="eyebrow">sandbox</div>
            <h2 id="sb-title">{{ t('graph.sbTitle') }}</h2>
          </div>

          <div class="dialog__body">
            <p class="muted" style="margin: 0">
              {{ t('graph.sbNote') }}
            </p>

            <div v-if="violations.length" class="error-banner" role="alert">
              <strong>{{ t('graph.sbBroken', { n: violations.length }) }}</strong>
              <ul style="margin: 6px 0 0; padding-left: 18px">
                <li v-for="v in violations" :key="`${v.before}-${v.after}`">
                  {{ t('graph.sbViolation', { before: labelOf(v.before), after: labelOf(v.after), why: v.why }) }}
                </li>
              </ul>
            </div>
            <div v-else class="info-banner" role="status">
              {{ t('graph.sbClean') }}
            </div>

            <ol class="chain chain--compact">
              <li
                v-for="(stage, index) in sandboxStages"
                :key="stage.name"
                class="node node--draggable"
                draggable="true"
                tabindex="0"
                :aria-label="t('graph.move', { label: stage.label, index: index + 1 })"
                @dragstart="onDragStart(stage.name)"
                @dragover.prevent
                @drop="onDrop(stage.name)"
                @keydown.up.prevent="onDrop(sandboxOrder[index - 1] ?? stage.name)"
                @keydown.down.prevent="onDrop(sandboxOrder[index + 1] ?? stage.name)"
              >
                <span class="node__marker">{{ index + 1 }}</span>
                <div class="node__body">
                  <span class="node__label">{{ stage.label }}</span>
                  <code class="node__name mono">{{ stage.name }}</code>
                </div>
              </li>
            </ol>
          </div>

          <div class="dialog__foot">
            <button class="btn ghost" type="button" @click="sandboxOrder = stages.map((s) => s.name); violations = []">
              {{ t('graph.reset') }}
            </button>
            <button class="btn lamp" type="button" @click="closeSandbox">{{ t('graph.close') }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.graph {
  display: grid;
  gap: 12px;
}

.graph__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.chain {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 0;
}

.node {
  position: relative;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 10px;
  padding: 5px 0;
}

/* The connector. Drawn per-node rather than as one long rule so it can stop at the
   halted stage — a line that continues past the halt implies the message kept going. */
.node:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 12px;
  top: 22px;
  bottom: -6px;
  width: 1px;
  background: var(--border-strong);
}

.node__marker {
  position: relative;
  z-index: 1;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  font-family: var(--mono);
  font-size: 10px;
  color: var(--ink-3);
}

.node--slow .node__marker {
  border-color: var(--brand);
  color: var(--brand);
  background: var(--brand-soft);
}

.node--halted .node__marker {
  border-color: var(--danger);
  color: var(--danger);
  background: var(--danger-soft);
}

.node--idle .node__marker {
  opacity: 0.55;
}

.node__body {
  display: grid;
  gap: 3px;
  padding: 0 0 6px;
}

.node__title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-height: 24px;
}

.node__label {
  font-size: 12.5px;
  color: var(--ink);
}

.node__name {
  font-size: 10px;
  color: var(--ink-3);
}

.node__timing {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 64px;
  align-items: center;
  gap: 8px;
}

.node__bar {
  height: 5px;
  border-radius: 3px;
  background: var(--surface-3);
  overflow: hidden;
}

.node__fill {
  display: block;
  height: 100%;
  background: var(--chart-1);
  border-radius: 3px;
}

.node--slow .node__fill {
  background: var(--chart-3);
}

.node__ms {
  font-size: 10.5px;
  color: var(--ink-2);
  text-align: right;
}

.graph__foot {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--ink-2);
}

/* ------------------------------------------------------------------ sandbox */

.chain--compact {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--surface-2);
  max-height: 320px;
  overflow-y: auto;
}

.node--draggable {
  cursor: grab;
  border-radius: 6px;
  padding: 4px 6px;
}

.node--draggable:not(:last-child)::before {
  left: 18px;
}

.node--draggable:hover {
  background: var(--surface-3);
}

.node--draggable:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: -1px;
}

.node--draggable:active {
  cursor: grabbing;
}

.dialog--wide {
  width: min(620px, calc(100vw - 32px));
}
</style>
