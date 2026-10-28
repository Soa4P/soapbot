<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api, type MessageTrace, type PipelineTopology, type TraceSummary } from '@/api/client'
import StageGraph from '@/components/StageGraph.vue'
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
      <h2>链路追踪</h2>
      <span class="tag">{{ traces.length }} 条</span>
      <span v-if="summary" class="tag">
        保留 {{ summary.traces_kept }} 条 · 重启即清空
      </span>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" :disabled="loading" @click="loadTraces()">
        {{ loading ? '读取中…' : '刷新' }}
      </button>
      <button class="btn" :class="live ? 'lamp' : 'ghost'" type="button" @click="toggleLive">
        {{ live ? '停止跟随' : '每 4 秒跟随' }}
      </button>
    </div>

    <div class="panel__body split">
      <div class="split__list">
        <p v-if="!traces.length" class="empty">
          缓冲区为空。消息处理后会出现在这里——若是刚启动，先发一条消息试试。
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
              <span v-if="trace.halted" class="tag bad">中止</span>
            </button>
          </li>
        </ul>
      </div>

      <div class="split__detail">
        <template v-if="selected">
          <div class="detail__head">
            <div>
              <div class="eyebrow">trace {{ selected.trace_id.slice(0, 12) }}</div>
              <h3 class="detail__title mono">{{ selected.session_key || '（无会话键）' }}</h3>
            </div>
            <div class="row">
              <span class="pill" :class="selected.halted ? 'bad' : 'ok'">
                <i class="dot" />{{ selected.halted ? '已中止' : '已完成' }}
              </span>
              <span class="tag">{{ fmtMs(selected.total_ms) }}</span>
            </div>
          </div>

          <p v-if="selected.halted" class="warn-banner" style="margin: 8px 0 0">
            在 <code class="mono">{{ haltedLabel || '未知环节' }}</code> 中止：该环节的
            <code class="mono">StageResult.halt</code> 为真，后续环节没有执行。
          </p>

          <div v-if="topology" style="margin-top: 10px">
            <StageGraph
              :stages="topology.stages"
              :constraints="topology.constraints"
              :timings="selected.stages"
              :halted-at="haltedLabel"
            />
          </div>
        </template>

        <p v-else class="empty">从左侧选一条消息查看逐环节耗时。</p>
      </div>
    </div>
  </section>

  <section v-if="topology" class="panel">
    <div class="panel__head">
      <h2>环节约束</h2>
      <span class="tag">{{ topology.constraints.length }} 条</span>
    </div>
    <div class="panel__body flush">
      <table class="data">
        <caption class="visually-hidden">流水线环节之间的顺序约束</caption>
        <thead>
          <tr>
            <th scope="col">必须在前</th>
            <th scope="col">必须在后</th>
            <th scope="col">原因</th>
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
</style>
