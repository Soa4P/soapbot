<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { api } from '@/api/client'
import EmptyState from '@/components/EmptyState.vue'
import { t } from '@/i18n'
import { clock } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

/**
 * Tail of the in-process ring buffer, not the log file.
 *
 * The API serves a bounded ring on purpose (see `recent_logs`): a file endpoint
 * would let a caller walk arbitrary amounts of disk, and the file may not exist on
 * a read-only container. So this page can only ever show the recent window — which
 * is the right limitation for a "what just happened" view, and wrong for an audit
 * trail. The Security page is the audit trail.
 */
const level = ref('')
const contains = ref('')
const limit = ref(200)

/**
 * Hard ceiling on how much of the ring this page will ask for.
 *
 * "Load more" is a convenience, not a way to page through the whole file — the endpoint
 * serves a bounded ring precisely so that no caller can walk arbitrary amounts of it. The
 * cap makes that boundary visible in the UI instead of letting the button fail at 2000
 * with a 422 the operator cannot interpret.
 */
const LIMIT_STEP = 200
const LIMIT_MAX = 1000

const logs = useAsync(() =>
  api.logs({ limit: limit.value, level: level.value, contains: contains.value }),
)

// Debounced rather than per-keystroke: this is a server round-trip into a Python
// process, and typing "error" would otherwise issue five full ring copies.
let timer: ReturnType<typeof setTimeout> | undefined
watch([level, contains, limit], () => {
  clearTimeout(timer)
  timer = setTimeout(() => void logs.reload(), 250)
})

// The debounce timer outlives the component if it is not cleared. Navigating away within
// 250 ms of typing leaves a pending callback that fires against a disposed hook — a
// reload nobody asked for, on a page that no longer exists, in the middle of the next
// page's first paint.
onBeforeUnmount(() => clearTimeout(timer))

const canLoadMore = computed(() => limit.value < LIMIT_MAX)

function loadMore(): void {
  limit.value = Math.min(limit.value + LIMIT_STEP, LIMIT_MAX)
}

const entries = computed<any[]>(() => logs.data.value?.entries ?? [])
const total = computed<number>(() => logs.data.value?.total ?? 0)
const restricted = computed(() => Boolean(logs.data.value?.details_restricted))
const issues = computed<number>(() => logs.data.value?.issues ?? 0)
const showDetails = ref(false)

// Labels for the filter, not for the rows. The log text itself stays exactly as the
// logger wrote it — translating it would make the panel disagree with the file that
// `grep` and the alert rules read.
const levels = computed(() => [
  { value: '', label: t('common.all') },
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
])

function levelClass(value: string): string {
  const upper = String(value).toUpperCase()
  if (upper === 'ERROR' || upper === 'CRITICAL') return 'bad'
  if (upper === 'WARNING') return 'lamp'
  return ''
}

function detail(entry: any): string {
  const extra = entry.fields ?? entry.extra ?? {}
  const parts = Object.entries(extra)
    .filter(([key]) => !['level', 'msg', 'time', 'timestamp'].includes(key))
    .map(([key, value]) => `${key}=${value}`)
  return parts.join(' ')
}
</script>

<template>
  <section class="panel">
    <div class="panel__body">
      <div class="eyebrow">{{ t('logs.diagnosis') }}</div>
      <h2>{{ issues ? t('logs.issuesFound', { count: issues }) : t('logs.noIssues') }}</h2>
      <p class="hint">{{ t('logs.nextStep') }}</p>
      <p v-if="restricted" class="hint">{{ t('logs.restricted') }}</p>
    </div>
  </section>
  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('logs.title') }}</h2>
      <span class="tag">{{ entries.length }} / {{ total }}</span>
      <span class="strip__spacer" />
      <select v-if="!restricted" v-model="level" class="field" style="width: 140px" :aria-label="t('logs.level')">
        <option v-for="item in levels" :key="item.value" :value="item.value">
          {{ item.label }}
        </option>
      </select>
      <input
        v-if="!restricted"
        v-model="contains"
        class="field"
        style="width: 220px"
        :placeholder="t('logs.placeholder')"
        maxlength="200"
      />
      <button v-if="!restricted && entries.length" class="btn ghost" type="button" @click="showDetails = !showDetails">
        {{ showDetails ? t('logs.hideDetails') : t('logs.showDetails') }}
      </button>
      <button class="btn ghost" :disabled="logs.loading.value" @click="logs.reload()">
        {{ t('common.refresh') }}
      </button>
      <button
        v-if="canLoadMore && entries.length"
        class="btn ghost"
        type="button"
        :disabled="logs.loading.value"
        @click="loadMore"
      >
        {{ t('common.loadMore') }}
      </button>
    </div>
    <div class="panel__body flush">
      <div v-if="logs.error.value" class="panel__body">
        <div class="error-banner">{{ logs.error.value }}</div>
      </div>
      <div v-else-if="logs.loading.value && !entries.length" class="empty">{{ t('common.loading') }}</div>
      <div v-else-if="restricted" class="empty">{{ t('logs.restricted') }}</div>
      <EmptyState v-else-if="!entries.length" :lead="t('logs.empty')" :hint="t('logs.emptyHint')" />
      <div v-else class="scroll" style="max-height: 640px">
        <table class="data"><caption class="visually-hidden">{{ t('logs.title') }}</caption>
          <thead>
            <tr>
              <th scope="col" style="width: 92px">{{ t('common.time') }}</th>
              <th scope="col" style="width: 84px">{{ t('logs.level') }}</th>
              <th scope="col">{{ t('common.content') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(entry, index) in entries" :key="index">
              <td class="key" style="white-space: nowrap">{{ clock(entry.time ?? entry.timestamp) }}</td>
              <td>
                <span class="tag" :class="levelClass(entry.level)">{{ entry.level }}</span>
              </td>
              <td>
                {{ entry.msg }}
                <span v-if="showDetails && detail(entry)" class="hint"> {{ detail(entry) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
