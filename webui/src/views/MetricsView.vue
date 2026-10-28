<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api, type MetricsResponse, type TraceSummary } from '@/api/client'
import BarChart from '@/components/charts/BarChart.vue'
import LineChart from '@/components/charts/LineChart.vue'
import { clock } from '@/lib/format'

/**
 * 10 — throughput and latency over the ring buffer's window.
 *
 * Everything here is derived from the same samples the traces produced, so the two
 * pages can never disagree about how many messages were handled. That is the reason
 * this page does not query the runtime counters separately: two sources for one number
 * is how a dashboard starts contradicting itself.
 */
const data = ref<MetricsResponse | null>(null)
const summary = ref<TraceSummary | null>(null)
const error = ref('')

async function load(): Promise<void> {
  try {
    const body = await api.pipelineMetrics(720)
    data.value = body
    summary.value = body.summary
    error.value = ''
  } catch (err) {
    error.value = (err as Error).message
  }
}

const labels = computed(() => (data.value?.samples ?? []).map((s) => clock(s.ts)))

const latencySeries = computed(() => [
  {
    key: 'p50',
    label: 'p50',
    values: (data.value?.samples ?? []).map((s) => s.p50_ms),
    tone: 'brand' as const,
  },
  {
    key: 'p95',
    label: 'p95',
    values: (data.value?.samples ?? []).map((s) => s.p95_ms),
    tone: 'warn' as const,
  },
  {
    key: 'max',
    label: '最长',
    values: (data.value?.samples ?? []).map((s) => s.max_ms),
    tone: 'danger' as const,
  },
])

const throughputSeries = computed(() => [
  {
    key: 'handled',
    label: '已处理',
    values: (data.value?.samples ?? []).map((s) => s.handled),
    tone: 'ok' as const,
  },
  {
    key: 'halted',
    label: '被拦截',
    values: (data.value?.samples ?? []).map((s) => s.halted),
    tone: 'muted' as const,
  },
])

/** Reasons are not stored per count, so this chart shows totals rather than a breakdown.

 * Rendering an invented distribution would be worse than showing three bars; the
 * breakdown lives in page 04 (audit) where it is recorded per event.
 */
const counters = computed(() => {
  const c = summary.value?.counters
  if (!c) return []
  return [
    { label: '已处理', value: c.handled, tone: 'ok' as const },
    { label: '被拦截', value: c.halted, tone: 'warn' as const },
    { label: '处理失败', value: c.failed, tone: 'danger' as const },
  ]
})

const hasSamples = computed(() => (data.value?.samples.length ?? 0) > 1)

let timer: number | undefined

onMounted(() => {
  void load()
  // 10 s against a 5 s sample interval: fast enough to feel live, slow enough that the
  // chart is not redrawn in the middle of a hover.
  timer = window.setInterval(() => void load(), 10_000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})

function fmtMs(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}

function fmtCount(value: number): string {
  return String(Math.round(value))
}
</script>

<template>
  <div v-if="error" class="error-banner" role="alert">{{ error }}</div>

  <section class="panel">
    <div class="panel__head">
      <h2>概览</h2>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" @click="load">刷新</button>
    </div>
    <div class="panel__body">
      <div class="grid cols-4">
        <div class="readout">
          <span class="readout__label">已处理</span>
          <span class="readout__value">{{ summary?.counters.handled ?? 0 }}</span>
        </div>
        <div class="readout">
          <span class="readout__label">p95 延迟</span>
          <span class="readout__value">{{ fmtMs(summary?.p95_ms ?? 0) }}</span>
        </div>
        <div class="readout">
          <span class="readout__label">最长一次</span>
          <span class="readout__value">{{ fmtMs(summary?.max_ms ?? 0) }}</span>
        </div>
        <div class="readout">
          <span class="readout__label">缓冲区</span>
          <span class="readout__value">
            {{ summary?.traces_kept ?? 0 }}<small>条</small>
          </span>
        </div>
      </div>

      <p class="hint" style="margin: 10px 0 0">
        采样间隔 5 秒，保留最近 720 个点（约 1 小时）。重启清空——
        <strong>这里不是历史，是「刚刚发生了什么」</strong>。历史结论请看 04 页审计日志。
      </p>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head"><h2>延迟分位</h2></div>
    <div class="panel__body">
      <LineChart
        v-if="hasSamples"
        title="延迟分位（毫秒）"
        y-label="越接近最长，说明抖动越大"
        :series="latencySeries"
        :labels="labels"
        :format="fmtMs"
      />
      <p v-else class="empty">
        还需要更多样本。至少两条消息处理完才会出现曲线——5 秒一次采样。
      </p>
    </div>
  </section>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head"><h2>累计处理</h2></div>
      <div class="panel__body">
        <LineChart
          v-if="hasSamples"
          title="累计计数"
          :series="throughputSeries"
          :labels="labels"
          :format="fmtCount"
          :height="180"
        />
        <p v-else class="empty">暂无样本</p>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head"><h2>结果分布</h2></div>
      <div class="panel__body">
        <BarChart
          title="自服务启动以来的累计计数"
          :items="counters"
          unit=" 条"
          empty-text="还没有消息经过流水线"
        />
      </div>
    </section>
  </div>
</template>
