<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
import { datetime, fromNow, num, uptime, untilFuture } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const runtime = useAsync(() => api.runtime())

// --- external tools (MCP) ---------------------------------------------------
// Shown here rather than on its own page: an MCP server that failed to start is a
// runtime fault, and putting it next to adapter health is what makes "the bot is up
// but some tools are missing" visible in one place.
const mcp = useAsync(() => api.mcp())
const mcpBusy = ref(false)

/**
 * The outcome of the last reconnect, stored as *data*, not as a finished sentence.
 *
 * Holding the rendered string meant a panel left open across a language switch kept
 * showing the old language until the button was pressed again — a small, very
 * confusing inconsistency. Storing the numbers and translating at render time costs
 * one computed and removes the whole class.
 */
type McpNote = { kind: 'ok'; tools: number } | { kind: 'partial'; broken: number } | { kind: 'error'; text: string }
const mcpNote = ref<McpNote | null>(null)

const mcpServers = computed<any[]>(() => mcp.data.value?.servers ?? [])

const mcpNoteText = computed(() => {
  const note = mcpNote.value
  if (!note) return ''
  if (note.kind === 'ok') return t('runtime.mcpReconnected', { n: note.tools })
  if (note.kind === 'partial') return t('runtime.mcpReconnectedPartial', { n: note.broken })
  return note.text
})

async function reconnectMcp() {
  mcpBusy.value = true
  mcpNote.value = null
  try {
    const result = await api.refreshMcp()
    const broken = (result.servers ?? []).filter((s: any) => s.error)
    // Report the outcome explicitly. A silent success would leave the operator
    // unsure whether the button did anything, which is the same failure the endpoint
    // was added to fix.
    mcpNote.value = broken.length
      ? { kind: 'partial', broken: broken.length }
      : { kind: 'ok', tools: result.tools ?? 0 }
    await mcp.reload()
  } catch (err) {
    mcpNote.value = { kind: 'error', text: err instanceof Error ? err.message : String(err) }
  } finally {
    mcpBusy.value = false
  }
}

const scheduler = computed<any>(() => runtime.data.value?.scheduler ?? {})
const metrics = computed<any>(() => runtime.data.value?.metrics ?? {})
const config = computed<any>(() => runtime.data.value?.config ?? {})

const adapterRows = computed<any[]>(() => {
  const map = runtime.data.value?.adapters ?? {}
  return Object.entries(map).map(([name, value]: [string, any]) => ({ name, ...value }))
})

const jobs = computed<any[]>(() => scheduler.value.jobs ?? [])
const cronJobs = computed<any[]>(() => scheduler.value.plugin_cron ?? [])

const startedFor = computed(() => {
  const started = Number(metrics.value.started_at ?? 0)
  if (!started) return '—'
  return uptime(Date.now() / 1000 - started)
})

const counters = computed(() => [
  { label: t('runtime.processUptime'), value: startedFor.value },
  { label: t('runtime.schedulerTicks'), value: num(scheduler.value.ticks) },
  { label: t('runtime.tickInterval'), value: `${scheduler.value.tick_seconds ?? 0}s` },
  { label: t('runtime.timezone'), value: scheduler.value.timezone ?? '—' },
])
</script>

<template>
  <div v-if="runtime.error.value" class="error-banner">{{ runtime.error.value }}</div>

  <div class="grid cols-4">
    <div v-for="item in counters" :key="item.label" class="readout">
      <span class="readout__label">{{ item.label }}</span>
      <span class="readout__value" style="font-size: 16px">{{ item.value }}</span>
    </div>
  </div>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('runtime.scheduler') }}</h2>
        <span class="pill" :class="scheduler.running ? 'ok' : 'bad'">
          <i class="dot" />{{ scheduler.running ? 'TICKING' : 'STOPPED' }}
        </span>
      </div>
      <div class="panel__body flush">
        <table v-if="jobs.length" class="data"><caption class="visually-hidden">{{ t('runtime.scheduler') }}</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">{{ t('runtime.purpose') }}</th>
              <th scope="col">{{ t('runtime.nextRun') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in jobs" :key="job.id">
              <td class="key">{{ job.id }}</td>
              <td>{{ job.name }}</td>
              <!-- A middot, not full-width parentheses: the full-width form is Chinese
                   typography and looks wrong around Latin digits in the English panel. -->
              <td v-if="job.next_run_at">{{ datetime(job.next_run_at) }} · {{ untilFuture(job.next_run_at) }}</td>
              <td v-else class="faint">—</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">{{ t('runtime.schedulerStopped') }}</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('runtime.cronJobs') }}</h2>
        <span class="tag">{{ cronJobs.length }}</span>
      </div>
      <div class="panel__body flush">
        <table v-if="cronJobs.length" class="data"><caption class="visually-hidden">{{ t('runtime.cronJobs') }}</caption>
          <thead>
            <tr>
              <th scope="col">{{ t('common.plugin') }}</th>
              <th scope="col">{{ t('common.task') }}</th>
              <th scope="col">{{ t('common.next') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in cronJobs" :key="`${job.plugin}:${job.name}`">
              <td class="key">{{ job.plugin }}</td>
              <td>{{ job.name }}</td>
              <td>{{ untilFuture(job.next_run_at) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">
          {{ t('runtime.noCron') }}
        </div>
      </div>
    </section>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('runtime.adapterHealth') }}</h2>
      <span class="tag">{{ adapterRows.length }}</span>
    </div>
    <div class="panel__body flush">
      <table v-if="adapterRows.length" class="data"><caption class="visually-hidden">{{ t('runtime.adapterHealth') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('common.name') }}</th>
            <th scope="col">{{ t('common.status') }}</th>
            <th scope="col">{{ t('runtime.connectedAt') }}</th>
            <th scope="col" class="num">{{ t('runtime.reconnects') }}</th>
            <th scope="col">{{ t('common.capability') }}</th>
            <th scope="col">{{ t('overview.lastError') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in adapterRows" :key="row.name">
            <td class="key">{{ row.display_name || row.name }}</td>
            <td>
              <span class="pill" :class="row.online ? 'ok' : 'bad'">
                <i class="dot" />{{ row.online ? t('overview.online') : t('overview.offline') }}
              </span>
            </td>
            <td v-if="row.connected_at">{{ datetime(row.connected_at) }} · {{ fromNow(row.connected_at) }}</td>
            <td v-else class="faint">—</td>
            <td class="num">{{ row.reconnect_attempts }}</td>
            <td>
              <span class="tag">{{ t('runtime.capabilityCount', { n: (row.capabilities ?? []).length }) }}</span>
            </td>
            <td>{{ row.last_error || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">{{ t('runtime.noAdapters') }}</div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('runtime.mcpTitle') }}</h2>
      <span class="tag">{{ t('runtime.mcpServers', { n: mcpServers.length }) }}</span>
      <button class="btn" :disabled="mcpBusy || !mcp.data.value?.configured" @click="reconnectMcp">
        {{ mcpBusy ? t('runtime.reconnecting') : t('runtime.reconnect') }}
      </button>
    </div>
    <div class="panel__body flush">
      <div v-if="mcp.data.value && !mcp.data.value.configured" class="empty">
        {{ t('runtime.mcpUnconfigured') }}
        <div class="mono" style="margin-top: 6px">config/mcp.yaml</div>
      </div>
      <table v-else-if="mcpServers.length" class="data">
        <caption class="visually-hidden">{{ t('runtime.mcpServersCaption') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('common.name') }}</th>
            <th scope="col">{{ t('common.status') }}</th>
            <th scope="col" class="num">{{ t('runtime.toolsCount') }}</th>
            <th scope="col">{{ t('runtime.minRole') }}</th>
            <th scope="col">{{ t('common.error') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in mcpServers" :key="row.name">
            <td class="key">{{ row.name }}</td>
            <td>
              <!-- "0 tools" and "server crashed" are the same empty row otherwise, and
                   they call for opposite fixes: configure more tools vs fix the binary. -->
              <span class="pill" :class="row.error ? 'bad' : 'ok'">
                <i class="dot" />{{ row.error ? t('common.failed') : t('common.ok') }}
              </span>
            </td>
            <td class="num">{{ row.tools }}</td>
            <td><span class="tag">{{ row.min_role }}</span></td>
            <td>{{ row.error || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">{{ t('runtime.noMcpServers') }}</div>
      <p v-if="mcpNoteText" class="hint" style="padding: 8px 14px">{{ mcpNoteText }}</p>
    </div>
  </section>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('runtime.configFiles') }}</h2>
      </div>
      <div class="panel__body">
        <table class="data" :aria-label="t('runtime.configFiles')">
          <tbody>
            <!-- `white-space: normal` overrides the table's global `nowrap`. An absolute
                 path has no spaces, so without it the cell cannot wrap and the table
                 grows past the panel — which is what it did, in both languages. -->
            <tr>
              <th scope="row">Provider</th>
              <td class="key" style="white-space: normal; word-break: break-all">{{ config.providers_file || '—' }}</td>
            </tr>
            <tr>
              <th scope="row">Adapter</th>
              <td class="key" style="white-space: normal; word-break: break-all">{{ config.adapters_file || '—' }}</td>
            </tr>
            <tr>
              <th scope="row">{{ t('runtime.pluginsLoaded') }}</th>
              <td class="num">{{ config.plugins_loaded ?? 0 }}</td>
            </tr>
          </tbody>
        </table>
        <p class="hint" style="margin: 10px 0 0">
          {{ t('runtime.configHint') }}
        </p>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('common.count') }}</h2>
      </div>
      <div class="panel__body">
        <table class="data" :aria-label="t('common.count')">
          <tbody>
            <tr>
              <th scope="row">inbound</th>
              <td class="num">{{ num(metrics.inbound) }}</td>
            </tr>
            <tr>
              <th scope="row">handled</th>
              <td class="num">{{ num(metrics.handled) }}</td>
            </tr>
            <tr>
              <th scope="row">halted</th>
              <td class="num">{{ num(metrics.halted) }}</td>
            </tr>
            <tr>
              <th scope="row">failed</th>
              <td class="num">{{ num(metrics.failed) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
