<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { datetime, fromNow, num, uptime, untilFuture } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const runtime = useAsync(() => api.runtime())

// --- external tools (MCP) ---------------------------------------------------
// Shown here rather than on its own page: an MCP server that failed to start is a
// runtime fault, and putting it next to adapter health is what makes "the bot is up
// but some tools are missing" visible in one place.
const mcp = useAsync(() => api.mcp())
const mcpBusy = ref(false)
const mcpNote = ref('')
const mcpServers = computed<any[]>(() => mcp.data.value?.servers ?? [])

async function reconnectMcp() {
  mcpBusy.value = true
  mcpNote.value = ''
  try {
    const result = await api.refreshMcp()
    const broken = (result.servers ?? []).filter((s: any) => s.error)
    // Report the outcome explicitly. A silent success would leave the operator
    // unsure whether the button did anything, which is the same failure the endpoint
    // was added to fix.
    mcpNote.value = broken.length
      ? `已重连，${broken.length} 个服务器仍失败`
      : `已重连，共 ${result.tools ?? 0} 个工具`
    await mcp.reload()
  } catch (err) {
    mcpNote.value = err instanceof Error ? err.message : String(err)
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
  { label: '进程 uptime', value: startedFor.value },
  { label: '调度 tick', value: num(scheduler.value.ticks) },
  { label: 'tick 间隔', value: `${scheduler.value.tick_seconds ?? 0}s` },
  { label: '时区', value: scheduler.value.timezone ?? '—' },
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
        <h2>调度器</h2>
        <span class="pill" :class="scheduler.running ? 'ok' : 'bad'">
          <i class="dot" />{{ scheduler.running ? 'TICKING' : 'STOPPED' }}
        </span>
      </div>
      <div class="panel__body flush">
        <table v-if="jobs.length" class="data"><caption class="visually-hidden">调度器</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">用途</th>
              <th scope="col">下次运行</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in jobs" :key="job.id">
              <td class="key">{{ job.id }}</td>
              <td>{{ job.name }}</td>
              <td>{{ job.next_run_at ? `${datetime(job.next_run_at)}（${untilFuture(job.next_run_at)}）` : '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">调度器未运行：插件定时任务与额度过期清扫都不会执行。</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h2>插件定时任务</h2>
        <span class="tag">{{ cronJobs.length }}</span>
      </div>
      <div class="panel__body flush">
        <table v-if="cronJobs.length" class="data"><caption class="visually-hidden">插件定时任务</caption>
          <thead>
            <tr>
              <th scope="col">插件</th>
              <th scope="col">任务</th>
              <th scope="col">下次</th>
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
          没有已注册的定时任务。任务在插件加载后才会出现，且首次出现只排期、不立即执行。
        </div>
      </div>
    </section>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>适配器健康</h2>
      <span class="tag">{{ adapterRows.length }}</span>
    </div>
    <div class="panel__body flush">
      <table v-if="adapterRows.length" class="data"><caption class="visually-hidden">适配器健康</caption>
        <thead>
          <tr>
            <th scope="col">名称</th>
            <th scope="col">状态</th>
            <th scope="col">连接时间</th>
            <th scope="col" class="num">重连</th>
            <th scope="col">能力</th>
            <th scope="col">最近错误</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in adapterRows" :key="row.name">
            <td class="key">{{ row.display_name || row.name }}</td>
            <td>
              <span class="pill" :class="row.online ? 'ok' : 'bad'">
                <i class="dot" />{{ row.online ? '在线' : '离线' }}
              </span>
            </td>
            <td>{{ row.connected_at ? `${datetime(row.connected_at)}（${fromNow(row.connected_at)}）` : '—' }}</td>
            <td class="num">{{ row.reconnect_attempts }}</td>
            <td>
              <span class="tag">{{ (row.capabilities ?? []).length }} 项</span>
            </td>
            <td>{{ row.last_error || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">未注册任何适配器。</div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>外部工具（MCP）</h2>
      <span class="tag">{{ mcpServers.length }} 个服务器</span>
      <button class="btn" :disabled="mcpBusy || !mcp.data.value?.configured" @click="reconnectMcp">
        {{ mcpBusy ? '重连中…' : '重连' }}
      </button>
    </div>
    <div class="panel__body flush">
      <p v-if="mcp.data.value && !mcp.data.value.configured" class="empty">
        未配置 MCP。在 <span class="mono">config/mcp.yaml</span> 里声明服务器后重启，或点「重连」重新枚举工具。
      </p>
      <table v-else-if="mcpServers.length" class="data">
        <caption class="visually-hidden">MCP 服务器</caption>
        <thead>
          <tr>
            <th scope="col">名称</th>
            <th scope="col">状态</th>
            <th scope="col" class="num">工具数</th>
            <th scope="col">最低角色</th>
            <th scope="col">错误</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in mcpServers" :key="row.name">
            <td class="key">{{ row.name }}</td>
            <td>
              <!-- "0 tools" and "server crashed" are the same empty row otherwise, and
                   they call for opposite fixes: configure more tools vs fix the binary. -->
              <span class="pill" :class="row.error ? 'bad' : 'ok'">
                <i class="dot" />{{ row.error ? '失败' : '正常' }}
              </span>
            </td>
            <td class="num">{{ row.tools }}</td>
            <td><span class="tag">{{ row.min_role }}</span></td>
            <td>{{ row.error || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">未配置任何 MCP 服务器。</div>
      <p v-if="mcpNote" class="hint">{{ mcpNote }}</p>
    </div>
  </section>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head">
        <h2>配置文件</h2>
      </div>
      <div class="panel__body">
        <table class="data" aria-label="配置文件">
          <tbody>
            <tr>
              <th scope="row">Provider</th>
              <td class="key">{{ config.providers_file || '—' }}</td>
            </tr>
            <tr>
              <th scope="row">Adapter</th>
              <td class="key">{{ config.adapters_file || '—' }}</td>
            </tr>
            <tr>
              <th scope="row">已加载插件</th>
              <td class="num">{{ config.plugins_loaded ?? 0 }}</td>
            </tr>
          </tbody>
        </table>
        <p class="hint" style="margin: 10px 0 0">
          配置文件只在启动时读取。修改后需要重启服务。
        </p>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h2>累计计数</h2>
      </div>
      <div class="panel__body">
        <table class="data" aria-label="累计计数">
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
