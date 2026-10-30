<script setup lang="ts">
import { computed } from 'vue'

import { api } from '@/api/client'
import SetupGuide from '@/components/SetupGuide.vue'
import { t } from '@/i18n'
import { compact, num, uptime } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const runtime = useAsync(() => api.runtime())
const providers = useAsync(() => api.providers())
const personas = useAsync(() => api.personas())
const bilibili = useAsync(() => api.bilibili())

const metrics = computed(() => runtime.data.value?.metrics ?? {})

const adapters = computed<any[]>(() => {
  const map = runtime.data.value?.adapters ?? {}
  return Object.entries(map).map(([name, value]: [string, any]) => ({ name, ...value }))
})

// Labels are built inside the computed so switching language re-renders them. A
// module-level array would freeze the labels at import time.
const flags = computed(() => {
  const config = runtime.data.value?.config ?? {}
  return [
    { label: t('overview.memory'), on: Boolean(config.memory_enabled) },
    { label: t('overview.budget'), on: Boolean(config.budget_enabled) },
    { label: t('overview.bilibili'), on: Boolean(bilibili.data.value?.enabled) },
    { label: t('overview.isolation'), on: Boolean(config.plugin_isolation) },
  ]
})

const startupErrors = computed<string[]>(() => runtime.data.value?.startup_errors ?? [])

const haltRate = computed(() => {
  const inbound = Number(metrics.value.inbound ?? 0)
  const halted = Number(metrics.value.halted ?? 0)
  if (!inbound) return '—'
  return `${((halted / inbound) * 100).toFixed(1)}%`
})

const readouts = computed(() => [
  { label: t('overview.inbound'), value: num(metrics.value.inbound) },
  { label: t('common.processed'), value: num(metrics.value.handled) },
  { label: t('common.intercepted'), value: num(metrics.value.halted), foot: haltRate.value },
  { label: t('common.failed'), value: num(metrics.value.failed) },
])

const runningFor = computed(() => {
  const started = Number(metrics.value.started_at ?? 0)
  if (!started) return t('overview.notStarted')
  return uptime(Date.now() / 1000 - started)
})

const providerRows = computed<any[]>(() => providers.data.value?.providers ?? [])
const providerStats = computed<Record<string, any>>(() => providers.data.value?.stats ?? {})
</script>

<template>
  <!-- First, before any readout: a missing provider makes every number below meaningless,
       and an operator's first question is "why does it not answer", not "what is the
       inbound rate". The card hides itself once the five checks pass. -->
  <SetupGuide />

  <div v-if="runtime.error.value" class="error-banner">
    {{ runtime.error.value }}
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('overview.readouts') }}</h2>
      <span class="eyebrow">up {{ runningFor }}</span>
      <span class="strip__spacer" />
      <span class="pill" :class="runtime.data.value?.running ? 'ok' : 'bad'">
        <i class="dot" />{{ runtime.data.value?.running ? 'RUNNING' : 'IDLE' }}
      </span>
    </div>
    <div class="panel__body">
      <div class="grid cols-4">
        <div v-for="item in readouts" :key="item.label" class="readout">
          <span class="readout__label">{{ item.label }}</span>
          <span class="readout__value">
            {{ item.value }}<small v-if="item.foot">{{ item.foot }}</small>
          </span>
        </div>
      </div>
    </div>
  </section>

  <section v-if="startupErrors.length" class="panel">
    <div class="panel__head">
      <h2>{{ t('overview.startupWarnings') }}</h2>
      <span class="tag bad">{{ startupErrors.length }}</span>
    </div>
    <div class="panel__body stack">
      <div v-for="(item, index) in startupErrors" :key="index" class="error-banner">
        {{ item }}
      </div>
      <p class="hint" style="margin: 0">
        {{ t('overview.startupHintLead') }}
        <span class="mono">config/adapters.yaml</span>{{ t('overview.startupHintTail') }}
      </p>
    </div>
  </section>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('overview.adapters') }}</h2>
        <span class="tag">{{ adapters.length }}</span>
      </div>
      <div class="panel__body flush">
        <table v-if="adapters.length" class="data"><caption class="visually-hidden">{{ t('overview.adapters') }}</caption>
          <thead>
            <tr>
              <th scope="col">{{ t('common.name') }}</th>
              <th scope="col">{{ t('overview.protocol') }}</th>
              <th scope="col">{{ t('common.status') }}</th>
              <th scope="col">{{ t('overview.lastError') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="adapter in adapters" :key="adapter.name">
              <td class="key">{{ adapter.name }}</td>
              <td>{{ adapter.protocol || '—' }}</td>
              <td>
                <span class="pill" :class="adapter.online ? 'ok' : 'bad'">
                  <i class="dot" />{{ adapter.online ? t('overview.online') : t('overview.offline') }}
                </span>
              </td>
              <td>{{ adapter.last_error || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <!-- The file to edit gets its own line instead of being embedded mid-sentence:
             it is the only actionable part, and a sentence split around a path breaks
             as soon as a language orders the clause differently. -->
        <div v-else class="empty">
          {{ t('overview.noAdapters') }}
          <div class="mono" style="margin: 6px 0">config/adapters.yaml</div>
          {{ t('overview.fillAdapter') }}
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('overview.flags') }}</h2>
      </div>
      <div class="panel__body">
        <div class="grid cols-2">
          <div v-for="flag in flags" :key="flag.label" class="row">
            <span class="pill" :class="flag.on ? 'ok' : ''">
              <i class="dot" />{{ flag.on ? 'ON' : 'OFF' }}
            </span>
            <span class="mono" style="font-size: 12px">{{ flag.label }}</span>
          </div>
        </div>
        <p class="hint" style="margin: 12px 0 0">
          {{ t('overview.flagsHint') }}
        </p>
      </div>
    </section>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('overview.providers') }}</h2>
      <span class="tag">{{ providerRows.length }}</span>
    </div>
    <div class="panel__body flush">
      <table v-if="providerRows.length" class="data"><caption class="visually-hidden">{{ t('overview.providers') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('overview.priority') }}</th>
            <th scope="col">ID</th>
            <th scope="col">{{ t('common.model') }}</th>
            <th scope="col">{{ t('common.capability') }}</th>
            <th scope="col" class="num">{{ t('common.calls') }}</th>
            <th scope="col" class="num">{{ t('common.failed') }}</th>
            <th scope="col">{{ t('overview.cooldown') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in providerRows" :key="row.id">
            <td class="num">{{ row.priority }}</td>
            <td class="key">{{ row.label || row.id }}</td>
            <td>{{ row.model || '—' }}</td>
            <td>
              <span v-for="slot in row.slots" :key="slot" class="tag" style="margin-right: 4px">
                {{ slot }}
              </span>
            </td>
            <td class="num">{{ num(providerStats[row.id]?.calls) }}</td>
            <td class="num">{{ num(providerStats[row.id]?.failures) }}</td>
            <td>
              <span v-if="providerStats[row.id]?.cooling_down" class="tag bad">{{ t('overview.cooling') }}</span>
              <span v-else class="faint">—</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">
        {{ t('overview.noProviders') }}
        <div class="mono" style="margin: 6px 0">config/providers.yaml</div>
        {{ t('overview.fillProviders') }}
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('overview.personas') }}</h2>
      <span class="tag">{{ personas.data.value?.count ?? 0 }}</span>
    </div>
    <div class="panel__body">
      <div class="row">
        <span
          v-for="persona in personas.data.value?.personas ?? []"
          :key="persona.id"
          class="tag lamp"
        >
          {{ persona.id }}
        </span>
        <span v-if="!personas.data.value?.personas?.length" class="faint">
          {{ t('overview.noPersonas') }}
        </span>
      </div>
      <p class="hint" style="margin: 10px 0 0">
        {{ t('overview.defaultBinding') }}<span class="mono">{{
          personas.data.value?.binding?.global_default || t('overview.unset')
        }}</span>{{ t('overview.bindingRest', {
          groups: Object.keys(personas.data.value?.binding?.groups ?? {}).length,
          users: Object.keys(personas.data.value?.binding?.users ?? {}).length,
        }) }}
      </p>
    </div>
  </section>

  <p class="hint" style="margin: 0">
    {{ t('overview.footer', {
      handled: compact(metrics.handled),
      ticks: runtime.data.value?.scheduler?.ticks ?? 0,
    }) }}
  </p>
</template>
