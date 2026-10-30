<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api, type MessageTrace, type PipelineTopology, type TraceSummary } from '@/api/client'
import StageGraph from '@/components/StageGraph.vue'
import { t } from '@/i18n'
import { clock } from '@/lib/format'

/**
 * 09 — pipeline topology plus the trace of one message.
 *
 * The page exists to answer one question during an incident: "this reply took nine
 * seconds, where did the time go". Cumulative counters cannot answer it, which is why
 * the trace ring was added rather than reusing the existing runtime stats.
 *
 * Layout is master-detail: the list of recent messages on the left, the selected
 * message's stage breakdown on the right. Selecting is explicit (a click or Enter)
 * rather than following the newest row automatically — an autorefreshing panel that
 * also auto-selects will replace the trace you are reading every two seconds.
 */
const topology = ref<PipelineTopology | null>(null)
const traces = ref<MessageTrace[]>([])
const summary = ref<TraceSummary | null>(null)
const selected = ref<MessageTrace | null>(null)
const error = ref('')
const loading = ref(false)
const live = ref(false)
let timer: number | undefined

async function loadTopology(): Promise<void> {
  try {
    topology.value = await api.pipelineTopology()
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function loadTraces(keepSelection = true): Promise<void> {
  loading.value = true
  try {
    const body = await api.pipelineTraces(60)
    traces.value = body.traces
    summary.value = body.summary
    error.value = ''

    if (keepSelection && selected.value) {
      // Re-fetch by id: the trace may have been evicted, and a stale object kept in
      // local state would keep showing numbers that are no longer in the buffer.
      const still = body.traces.find((t) => t.trace_id === selected.value?.trace_id)
      selected.value = still ?? null
    } else if (!selected.value && body.traces.length) {
      selected.value = body.traces[0]
    }
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

function select(trace: MessageTrace): void {
  selected.value = trace
}

function toggleLive(): void {
  live.value = !live.value
  if (live.value) {
    timer = window.setInterval(() => void loadTraces(), 4000)
  } else if (timer) {
    window.clearInterval(timer)
    timer = undefined
  }
}

const haltedLabel = computed(() => {
  const trace = selected.value
  if (!trace || !trace.halted) return ''
  // `halt_reason` is either a stage name or `stage_error:<stage>`.
  return trace.halt_reason.startsWith('stage_error:')
    ? trace.halt_reason.replace('stage_error:', '')
    : trace.halt_reason
})

function fmtMs(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`
  return `${value.toFixed(value >= 10 ? 0 : 1)} ms`
}

const stream = computed(() => selected.value?.stream ?? {})
const chunks = computed(() => selected.value?.chunks ?? [])

/**
 * Whether the reply went out in pieces.
 *
 * Presence of the key, not a truthy value: the server always serialises `stream`, so
 * `{}` is the honest "this reply was not streamed" and `{count: 0}` would be a different
 * claim that never occurs.
 */
const streamed = computed(() => Object.keys(stream.value).length > 0)

/**
 * Whether the reply stage ran at all.
 *
 * Needed so a trace that halted before delivery does not get the "sent as one message"
 * line — that sentence would be a statement about a send that never happened.
 *
 * Derived from the stage list rather than from an extras flag: `to_dict` does not
 * serialise `extras`, and reading a field the API never sends is how a panel ends up
 * quietly rendering nothing (the first draft of this block did exactly that).
 */
const replyRan = computed(
  () => selected.value?.stages?.some((stage) => stage.name === 'reply') ?? false,
)

/**
 * The three timings, on a shared scale.
 *
 * Normalising all three against the whole reply is the point: the gap between the first
 * sentence and the total is then *geometric* rather than something the reader has to
 * subtract. 2% floor keeps a 0 ms row visible instead of looking like a missing bar.
 */
const ladder = computed(() => {
  const stats = stream.value
  const total = Math.max(
    Number(stats.total_ms ?? 0),
    Number(selected.value?.total_ms ?? 0),
    1,
  )
  // The tones carry the reading: grey = the model was talking but the user had nothing,
  // blue = the moment they got something, faint = the full span those two sit inside.
  const rows: { key: string; ms: number; pct: number; tone: string }[] = []
  const add = (key: string, value: unknown, tone: string): void => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return
    rows.push({
      key,
      tone,
      ms: value,
      pct: Math.max(2, Math.min(100, (value / total) * 100)),
    })
  }
  add('pipeline.firstToken', stats.first_token_ms, 'silent')
  add('pipeline.firstSend', stats.first_send_ms, 'visible')
  add('pipeline.wholeReply', total, 'span')
  return rows
})

onMounted(() => {
  void loadTopology()
  void loadTraces(false)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div v-if="error" class="error-banner" role="alert">{{ error }}</div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('pipeline.title') }}</h2>
      <span class="tag">{{ t('common.rows', { n: traces.length }) }}</span>
      <span v-if="summary" class="tag">
        {{ t('pipeline.kept', { n: summary.traces_kept }) }}
      </span>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" :disabled="loading" @click="loadTraces()">
        {{ loading ? t('pipeline.reading') : t('common.refresh') }}
      </button>
      <button class="btn" :class="live ? 'lamp' : 'ghost'" type="button" @click="toggleLive">
        {{ live ? t('pipeline.stopFollow') : t('pipeline.follow') }}
      </button>
    </div>

    <div class="panel__body split">
      <div class="split__list">
        <p v-if="!traces.length" class="empty">
          {{ t('pipeline.empty') }}
        </p>

        <ul v-else class="msglist">
          <li v-for="trace in traces" :key="trace.trace_id">
            <button
              type="button"
              class="msgrow"
              :class="{ 'msgrow--active': trace.trace_id === selected?.trace_id }"
              :aria-pressed="trace.trace_id === selected?.trace_id"
              @click="select(trace)"
            >
              <span class="msgrow__time mono">{{ clock(trace.ts) }}</span>
              <span class="msgrow__bar">
                <span
                  class="msgrow__fill"
                  :class="{ 'msgrow__fill--slow': trace.total_ms > 1000 }"
                  :style="{ width: `${Math.min(100, (trace.total_ms / 2000) * 100)}%` }"
                />
              </span>
              <span class="msgrow__ms mono">{{ fmtMs(trace.total_ms) }}</span>
              <span v-if="trace.halted" class="tag bad">{{ t('pipeline.stopped') }}</span>
            </button>
          </li>
        </ul>
      </div>

      <div class="split__detail">
        <template v-if="selected">
          <div class="detail__head">
            <div>
              <div class="eyebrow">trace {{ selected.trace_id.slice(0, 12) }}</div>
              <h3 class="detail__title mono">{{ selected.session_key || t('pipeline.noSession') }}</h3>
            </div>
            <div class="row">
              <span class="pill" :class="selected.halted ? 'bad' : 'ok'">
                <i class="dot" />{{ selected.halted ? t('pipeline.stopped') : t('pipeline.completed') }}
              </span>
              <span class="tag">{{ fmtMs(selected.total_ms) }}</span>
            </div>
          </div>

          <!-- One sentence with the stage name as a placeholder, rather than two
               fragments around a <code> token. Monospace was doing less work here than
               the sentence being translatable as a unit. -->
          <p v-if="selected.halted" class="warn-banner" style="margin: 8px 0 0">
            {{ t('pipeline.halted', { stage: haltedLabel || t('pipeline.unknownStage') }) }}
          </p>

          <div v-if="topology" style="margin-top: 10px">
            <StageGraph
              :stages="topology.stages"
              :constraints="topology.constraints"
              :timings="selected.stages"
              :halted-at="haltedLabel"
            />
          </div>

          <!-- Streaming, below the stage graph: first *where* the time went, then
               *what the user actually saw while waiting*. Gated on `replyRan` so a
               trace that halted earlier gets no block rather than a box reading
               "sent as one message" about a send that never happened. -->
          <section v-if="replyRan" class="stream" aria-live="off">
            <div class="stream__head">
              <span class="eyebrow">{{ t('pipeline.stream') }}</span>
              <span class="strip__spacer" />
              <template v-if="streamed">
                <span class="tag">{{ t('pipeline.streamSent', { n: chunks.length }) }}</span>
                <span v-if="stream.interrupted" class="tag bad">
                  {{ t('pipeline.streamInterrupted') }}
                </span>
                <span v-else-if="stream.truncated" class="tag warn">
                  {{ t('pipeline.streamTruncated') }}
                </span>
              </template>
            </div>

            <template v-if="streamed">
              <div class="ladder">
                <div v-for="row in ladder" :key="row.key" class="ladder__row">
                  <span class="ladder__label">{{ t(row.key) }}</span>
                  <span class="ladder__track">
                    <span
                      class="ladder__fill"
                      :class="`ladder__fill--${row.tone}`"
                      :style="{ width: `${row.pct}%` }"
                    />
                  </span>
                  <span class="ladder__ms mono">{{ fmtMs(row.ms) }}</span>
                </div>
              </div>

              <p class="stream__note">{{ t('pipeline.streamNote') }}</p>

              <ol v-if="chunks.length" class="chunks">
                <li v-for="(chunk, index) in chunks" :key="index" class="chunk">
                  <span class="chunk__n mono">{{ index + 1 }}</span>
                  <!-- Single line with `title`: a long sentence would otherwise push the
                       detail column wider than the list it sits next to. -->
                  <span class="chunk__text" :title="chunk">{{ chunk }}</span>
                </li>
              </ol>
            </template>

            <p v-else class="stream__note">{{ t('pipeline.notStreamed') }}</p>
          </section>
        </template>

        <p v-else class="empty">{{ t('pipeline.pickOne') }}</p>
      </div>
    </div>
  </section>

  <section v-if="topology" class="panel">
    <div class="panel__head">
      <h2>{{ t('pipeline.constraints') }}</h2>
      <span class="tag">{{ t('common.rows', { n: topology.constraints.length }) }}</span>
    </div>
    <div class="panel__body flush">
      <table class="data">
        <caption class="visually-hidden">{{ t('pipeline.constraintsCaption') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('pipeline.before') }}</th>
            <th scope="col">{{ t('pipeline.after') }}</th>
            <th scope="col">{{ t('pipeline.why') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in topology.constraints" :key="`${c.before}-${c.after}`">
            <td class="key">{{ c.before }}</td>
            <td>{{ c.after }}</td>
            <td style="white-space: normal">{{ c.why }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.split {
  display: grid;
  grid-template-columns: minmax(0, 320px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

@media (max-width: 1000px) {
  .split {
    grid-template-columns: minmax(0, 1fr);
  }
}

.msglist {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 2px;
  max-height: 520px;
  overflow-y: auto;
}

.msgrow {
  width: 100%;
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) 56px auto;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: var(--ink-2);
}

.msgrow:hover {
  background: var(--surface-3);
}

.msgrow--active {
  border-color: var(--brand);
  background: var(--brand-soft);
  color: var(--ink);
}

.msgrow__time {
  font-size: 10.5px;
  color: var(--ink-3);
}

.msgrow__bar {
  height: 5px;
  border-radius: 3px;
  background: var(--surface-3);
  overflow: hidden;
}

.msgrow__fill {
  display: block;
  height: 100%;
  background: var(--chart-1);
}

.msgrow__fill--slow {
  background: var(--chart-3);
}

.msgrow__ms {
  font-size: 10.5px;
  text-align: right;
}

.detail__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.detail__title {
  font-size: 13px;
  margin: 2px 0 0;
  word-break: break-all;
}

/* ---------------------------------------------------------------- streaming */

.stream {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  animation: stream-in 160ms ease-out both;
}

.stream__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.stream__note {
  margin: 6px 0 0;
  font-size: 11px;
  line-height: 1.55;
  color: var(--ink-3);
}

.ladder {
  display: grid;
  gap: 5px;
  margin-top: 9px;
}

.ladder__row {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr) 62px;
  align-items: center;
  gap: 8px;
}

.ladder__label {
  font-size: 11px;
  color: var(--ink-2);
}

.ladder__track {
  height: 6px;
  border-radius: 3px;
  background: var(--surface-3);
  overflow: hidden;
}

.ladder__fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  transition: width 240ms ease-out;
}

.ladder__fill--silent {
  background: var(--ink-3);
}

.ladder__fill--visible {
  background: var(--chart-1);
}

.ladder__fill--span {
  background: var(--chart-grid);
}

.ladder__ms {
  font-size: 10.5px;
  color: var(--ink-2);
  text-align: right;
}

.chunks {
  display: grid;
  gap: 1px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  /* Twelve rows; past that the list scrolls so a chatty reply cannot push the
     stage graph off the screen. */
  max-height: 216px;
  overflow-y: auto;
}

.chunk {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 6px;
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 11.5px;
  color: var(--ink);
}

.chunk:hover {
  background: var(--surface-3);
}

.chunk__n {
  font-size: 10.5px;
  color: var(--ink-3);
  text-align: right;
}

.chunk__text {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

@keyframes stream-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .stream,
  .ladder__fill {
    animation: none;
    transition: none;
  }
}
</style>
