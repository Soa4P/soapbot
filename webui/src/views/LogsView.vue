<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
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

const levels = [
  { value: '', label: '全部' },
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
]

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
      <h2>运行日志</h2>
      <span class="tag">{{ entries.length }} / {{ total }}</span>
      <span class="strip__spacer" />
      <select v-model="level" class="field" style="width: 140px">
        <option v-for="item in levels" :key="item.value" :value="item.value">
          {{ item.label }}
        </option>
      </select>
      <input
        v-model="contains"
        class="field"
        style="width: 220px"
        placeholder="包含关键词"
        maxlength="200"
      />
      <button class="btn ghost" :disabled="logs.loading.value" @click="logs.reload()">
        刷新
      </button>
    </div>
    <div class="panel__body flush">
      <div v-if="logs.error.value" class="panel__body">
        <div class="error-banner">{{ logs.error.value }}</div>
      </div>
      <div v-else-if="logs.loading.value && !entries.length" class="empty">载入中…</div>
      <div v-else-if="!entries.length" class="empty">
        环形缓冲区为空。若刚启动服务，第一条日志会在首次请求后出现。
      </div>
      <div v-else class="scroll" style="max-height: 640px">
        <table class="data"><caption class="visually-hidden">运行日志</caption>
          <thead>
            <tr>
              <th scope="col" style="width: 92px">时间</th>
              <th scope="col" style="width: 84px">级别</th>
              <th scope="col">内容</th>
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
