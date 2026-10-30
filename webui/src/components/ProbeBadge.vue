<script setup lang="ts">
import { computed } from 'vue'

import type { AdapterProbeResult, ProbeResult } from '@/api/client'
import { t } from '@/i18n'

/**
 * One probe result, rendered inline next to the button that produced it.
 *
 * Deliberately a badge and not a dialog: an operator testing four provider rows wants
 * four answers side by side, not four modals to dismiss. Nothing is logged anywhere by
 * the UI — a probe result is transient by design, and a "connection history" panel would
 * quietly become a record of which internal hosts exist.
 *
 * The wording comes from structured fields (`state`, `status_code`), never from the
 * server's `hint`, because the hint is Chinese-only: it is for `doctor` and for `curl`,
 * and rendering it here would leave English operators with a half-translated panel.
 */
const props = defineProps<{ result: ProbeResult | AdapterProbeResult | null }>()

type Code =
  | 'ok'
  | 'authRejected'
  | 'notfound'
  | 'serverError'
  | 'unreachable'
  | 'error'
  | 'handshake_ok'
  | 'unauthorized'
  | 'not_onebot'
  | 'free'
  | 'in_use'

/** Green means "nothing for you to do"; amber means "reachable, but look here". */
const TONE: Record<Code, 'ok' | 'warn' | 'bad'> = {
  ok: 'ok',
  handshake_ok: 'ok',
  free: 'ok',
  in_use: 'ok',
  // A 401 proves the endpoint is alive; it still means the key is wrong.
  authRejected: 'warn',
  notfound: 'warn',
  serverError: 'warn',
  unauthorized: 'bad',
  not_onebot: 'bad',
  unreachable: 'bad',
  error: 'bad',
}

const code = computed<Code>(() => {
  const result = props.result
  if (!result) return 'error'

  const adapter = result as AdapterProbeResult
  if (adapter.state) {
    // The adapter probe already classified itself; trusting it keeps one source of truth.
    return (adapter.state in TONE ? adapter.state : 'error') as Code
  }

  if (result.error && !result.reachable) return 'unreachable'
  const status = result.status_code
  if (status === 401 || status === 403) return 'authRejected'
  if (status === 404) return 'notfound'
  if (status && status >= 500) return 'serverError'
  return result.ok ? 'ok' : 'error'
})

const label = computed(() => t(`probe.code.${code.value}`))
const tone = computed(() => TONE[code.value])
const detail = computed(() => (props.result as AdapterProbeResult | null)?.detail ?? '')

const meta = computed(() => {
  const result = props.result
  if (!result) return ''
  const parts: string[] = []
  if (result.status_code) parts.push(t('probe.http', { status: result.status_code }))
  parts.push(t('probe.elapsed', { ms: result.elapsed_ms }))
  return parts.join(' · ')
})
</script>

<template>
  <span v-if="result" class="probe">
    <span class="tag" :class="tone">{{ label }}</span>
    <span class="hint probe__meta">{{ meta }}</span>
    <span v-if="detail" class="hint probe__meta">{{ detail }}</span>
  </span>
</template>

<style scoped>
.probe {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
  flex-wrap: wrap;
}

/* Tabular figures so a column of timings does not jitter while it fills in. */
.probe__meta {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
