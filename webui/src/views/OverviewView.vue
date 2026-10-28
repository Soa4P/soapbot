<script setup lang="ts">
import { computed } from 'vue'

import { api } from '@/api/client'
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

const flags = computed(() => {
  const config = runtime.data.value?.config ?? {}
  return [
    { label: '记忆存储', on: Boolean(config.memory_enabled) },
    { label: '额度审批', on: Boolean(config.budget_enabled) },
    { label: 'B 站浏览', on: Boolean(bilibili.data.value?.enabled) },
    { label: '插件隔离', on: Boolean(config.plugin_isolation) },
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
  { label: '上行业务', value: num(metrics.value.inbound) },
  { label: '已处理', value: num(metrics.value.handled) },
  { label: '被拦截', value: num(metrics.value.halted), foot: haltRate.value },
  { label: '失败', value: num(metrics.value.failed) },
])

const runningFor = computed(() => {
  const started = Number(metrics.value.started_at ?? 0)
  if (!started) return '未启动'
  return uptime(Date.now() / 1000 - started)
})

const providerRows = computed<any[]>(() => providers.data.value?.providers ?? [])
const providerStats = computed<Record<string, any>>(() => providers.data.value?.stats ?? {})
</script>

<template>
  <div v-if="runtime.error.value" class="error-banner">
    {{ runtime.error.value }}
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>运行读数</h2>
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
      <h2>启动告警</h2>
      <span class="tag bad">{{ startupErrors.length }}</span>
    </div>
    <div class="panel__body stack">
      <div v-for="(item, index) in startupErrors" :key="index" class="error-banner">
        {{ item }}
      </div>
      <p class="hint" style="margin: 0">
        适配器构造失败时服务仍会启动：管理面板正是用来定位这个错误的地方。修改
        <span class="mono">config/adapters.yaml</span> 后重启生效。
      </p>
    </div>
  </section>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head">
        <h2>协议适配器</h2>
        <span class="tag">{{ adapters.length }}</span>
      </div>
      <div class="panel__body flush">
        <table v-if="adapters.length" class="data"><caption class="visually-hidden">协议适配器</caption>
          <thead>
            <tr>
              <th scope="col">名称</th>
              <th scope="col">协议</th>
              <th scope="col">状态</th>
              <th scope="col">最近错误</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="adapter in adapters" :key="adapter.name">
              <td class="key">{{ adapter.name }}</td>
              <td>{{ adapter.protocol || '—' }}</td>
              <td>
                <span class="pill" :class="adapter.online ? 'ok' : 'bad'">
                  <i class="dot" />{{ adapter.online ? '在线' : '离线' }}
                </span>
              </td>
              <td>{{ adapter.last_error || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">
          尚未配置适配器。服务只会提供管理 API，不会收到任何 QQ 消息。
          <br />在 <span class="mono">config/adapters.yaml</span> 中填写协议端地址后重启。
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h2>能力开关</h2>
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
          B 站与额度默认关闭。开启前请确认对应的合规与授权前提。
        </p>
      </div>
    </section>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>Provider 故障转移链</h2>
      <span class="tag">{{ providerRows.length }}</span>
    </div>
    <div class="panel__body flush">
      <table v-if="providerRows.length" class="data"><caption class="visually-hidden">Provider 故障转移链</caption>
        <thead>
          <tr>
            <th scope="col">优先级</th>
            <th scope="col">ID</th>
            <th scope="col">模型</th>
            <th scope="col">能力</th>
            <th scope="col" class="num">调用</th>
            <th scope="col" class="num">失败</th>
            <th scope="col">冷却</th>
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
              <span v-if="providerStats[row.id]?.cooling_down" class="tag bad">冷却中</span>
              <span v-else class="faint">—</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">
        未配置 Provider，模型阶段被禁用 —— 机器人不会产生任何回复。
        <br />在 <span class="mono">config/providers.yaml</span> 中配置模型端点。
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>人格卡</h2>
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
          没有人格卡，将使用空系统提示。
        </span>
      </div>
      <p class="hint" style="margin: 10px 0 0">
        默认绑定：<span class="mono">{{
          personas.data.value?.binding?.global_default || '（未设置）'
        }}</span>
        · 群绑定 {{ Object.keys(personas.data.value?.binding?.groups ?? {}).length }} 个 ·
        用户绑定 {{ Object.keys(personas.data.value?.binding?.users ?? {}).length }} 个
      </p>
    </div>
  </section>

  <p class="hint" style="margin: 0">
    已处理 {{ compact(metrics.handled) }} 条 · 调度器 tick
    {{ runtime.data.value?.scheduler?.ticks ?? 0 }} 次
  </p>
</template>
