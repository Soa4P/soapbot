<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api, type MetricsResponse, type TraceSummary } from '@/api/client'
import BarChart from '@/components/charts/BarChart.vue'
import LineChart from '@/components/charts/LineChart.vue'
import { t } from '@/i18n'
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
    label: t('metrics.seriesMax'),
    values: (data.value?.samples ?? []).map((s) => s.max_ms),
    tone: 'danger' as const,
  },
])

const throughputSeries = computed(() => [
  {
    key: 'handled',
    label: t('common.processed'),
    values: (data.value?.samples ?? []).map((s) => s.handled),
    tone: 'ok' as const,
  },
  {
    key: 'halted',
    label: t('common.intercepted'),
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
    { label: t('common.processed'), value: c.handled, tone: 'ok' as const },
    { label: t('common.intercepted'), value: c.halted, tone: 'warn' as const },
    { label: t('metrics.seriesFailed'), value: c.failed, tone: 'danger' as const },
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
      <h2>{{ t('metrics.overview') }}</h2>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" @click="load">{{ t('common.refresh') }}</button>
    </div>
    <div class="panel__body">
      <div class="grid cols-4">
        <div class="readout">
          <span class="readout__label">{{ t('common.processed') }}</span>
          <span class="readout__value">{{ summary?.counters.handled ?? 0 }}</span>
        </div>
        <div class="readout">
          <span class="readout__label">{{ t('metrics.p95') }}</span>
          <span class="readout__value">{{ fmtMs(summary?.p95_ms ?? 0) }}</span>
        </div>
        <div class="readout">
          <span class="readout__label">{{ t('metrics.slowest') }}</span>
          <span class="readout__value">{{ fmtMs(summary?.max_ms ?? 0) }}</span>
        </div>
        <div class="readout">
          <span class="readout__label">{{ t('metrics.buffer') }}</span>
          <span class="readout__value">
            {{ summary?.traces_kept ?? 0 }}<small>{{ t('metrics.bufferUnit') }}</small>
          </span>
        </div>
      </div>

      <!-- Three complete sentences rather than one sentence split around a <strong>.
           Emphasis survives; the text stays translatable without reordering. -->
      <p class="hint" style="margin: 10px 0 0">
        {{ t('metrics.bufferNote') }}
        <strong>{{ t('metrics.bufferWarning') }}</strong>
        {{ t('metrics.bufferPointer') }}
      </p>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head"><h2>{{ t('metrics.latency') }}</h2></div>
    <div class="panel__body">
      <LineChart
        v-if="hasSamples"
        :title="t('metrics.latencyChartTitle')"
        :y-label="t('metrics.latencyChartHint')"
        :series="latencySeries"
        :labels="labels"
        :format="fmtMs"
      />
      <p v-else class="empty">
        {{ t('metrics.latencyEmpty') }}
      </p>
    </div>
  </section>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head"><h2>{{ t('metrics.cumulativeHandled') }}</h2></div>
      <div class="panel__body">
        <LineChart
          v-if="hasSamples"
          :title="t('common.count')"
          :series="throughputSeries"
          :labels="labels"
          :format="fmtCount"
          :height="180"
        />
        <p v-else class="empty">{{ t('metrics.noSamples') }}</p>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head"><h2>{{ t('metrics.distribution') }}</h2></div>
      <div class="panel__body">
        <BarChart
          :title="t('metrics.distributionTitle')"
          :items="counters"
          :unit="t('metrics.barUnit')"
          :empty-text="t('metrics.distributionEmpty')"
        />
      </div>
    </section>
  </div>
</template>
