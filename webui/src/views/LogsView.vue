<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
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

const entries = computed<any[]>(() => logs.data.value?.entries ?? [])
const total = computed<number>(() => logs.data.value?.total ?? 0)

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
    <div class="panel__head">
      <h2>{{ t('logs.title') }}</h2>
      <span class="tag">{{ entries.length }} / {{ total }}</span>
      <span class="strip__spacer" />
      <select v-model="level" class="field" style="width: 140px" :aria-label="t('logs.level')">
        <option v-for="item in levels" :key="item.value" :value="item.value">
          {{ item.label }}
        </option>
      </select>
      <input
        v-model="contains"
        class="field"
        style="width: 220px"
        :placeholder="t('logs.placeholder')"
        maxlength="200"
      />
      <button class="btn ghost" :disabled="logs.loading.value" @click="logs.reload()">
        {{ t('common.refresh') }}
      </button>
    </div>
    <div class="panel__body flush">
      <div v-if="logs.error.value" class="panel__body">
        <div class="error-banner">{{ logs.error.value }}</div>
      </div>
      <div v-else-if="logs.loading.value && !entries.length" class="empty">{{ t('common.loading') }}</div>
      <div v-else-if="!entries.length" class="empty">
        {{ t('logs.empty') }}
      </div>
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
                <span v-if="detail(entry)" class="hint"> {{ detail(entry) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
