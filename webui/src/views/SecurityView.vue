<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
import { datetime, num } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const kind = ref('')
const audit = useAsync(() => api.audit(300, kind.value))
const access = useAsync(() => api.access())

// ``useAsync`` already reloads on the global refresh signal; only the local filter
// needs its own trigger.
watch(kind, () => void audit.reload())

const events = computed<any[]>(() => [...(audit.data.value?.events ?? [])].reverse())

const counts = computed(() => {
  const list = audit.data.value?.events ?? []
  const deny = list.filter((e: any) => e.outcome === 'deny').length
  const block = list.filter((e: any) => e.outcome === 'block' || e.outcome === 'quarantine').length
  return { total: list.length, deny, block }
})

const kinds = ['authz', 'injection', 'memory', 'command', 'rate_limit', 'plugin', 'login']

function outcomeClass(outcome: string): string {
  if (outcome === 'deny') return 'bad'
  if (outcome === 'block' || outcome === 'quarantine') return 'bad'
  return 'ok'
}

const floors = computed<any[]>(() => access.data.value?.permissions ?? [])
const roles = computed<any[]>(() => access.data.value?.roles ?? [])
</script>

<template>
  <div class="grid cols-3">
    <div class="readout">
      <span class="readout__label">事件（窗口内）</span>
      <span class="readout__value">{{ num(counts.total) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">拒绝</span>
      <span class="readout__value" style="color: var(--danger)">{{ num(counts.deny) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">阻断 / 隔离</span>
      <span class="readout__value" style="color: var(--warn)">{{ num(counts.block) }}</span>
    </div>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>审计流</h2>
      <span class="strip__spacer" />
      <select v-model="kind" class="field" style="width: 180px" aria-label="按类型过滤">
        <option value="">全部类型</option>
        <option v-for="item in kinds" :key="item" :value="item">{{ item }}</option>
      </select>
    </div>
    <div class="panel__body flush">
      <div class="scroll">
        <table v-if="events.length" class="data"><caption class="visually-hidden">审计流</caption>
          <thead>
            <tr>
              <th scope="col">时间</th>
              <th scope="col">类型</th>
              <th scope="col">动作</th>
              <th scope="col">结果</th>
              <th scope="col">用户</th>
              <th scope="col">角色</th>
              <th scope="col">群</th>
              <th scope="col">详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="event in events" :key="`${event.ts}-${event.trace_id}-${event.action}`">
              <td style="white-space: nowrap">{{ datetime(event.ts) }}</td>
              <td>{{ event.kind }}</td>
              <td class="key" style="max-width: 220px">{{ event.action }}</td>
              <td>
                <span class="tag" :class="outcomeClass(event.outcome)">{{ event.outcome }}</span>
              </td>
              <td>{{ event.user_id || '—' }}</td>
              <td>{{ event.role || '—' }}</td>
              <td>{{ event.group_id || '—' }}</td>
              <td style="max-width: 380px">{{ event.detail || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">窗口内没有审计事件。</div>
      </div>
    </div>
  </section>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head">
        <h2>权限下限</h2>
        <span class="hint">展平角色：看到 approve_payment 属于 owner，就不用翻源码</span>
      </div>
      <div class="panel__body flush">
        <table class="data"><caption class="visually-hidden">权限下限</caption>
          <thead>
            <tr>
              <th scope="col">权限</th>
              <th scope="col">最低角色</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in floors" :key="row.name">
              <td class="key">{{ row.name }}</td>
              <td>
                <span class="tag" :class="row.min_role === 'owner' ? 'lamp' : ''">
                  {{ row.min_role }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h2>角色与授权名单</h2>
      </div>
      <div class="panel__body stack">
        <table class="data"><caption class="visually-hidden">角色与授权名单</caption>
          <thead>
            <tr>
              <th scope="col">角色</th>
              <th scope="col" class="num">Rank</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="role in roles" :key="role.name">
              <td class="key">{{ role.name }}</td>
              <td class="num">{{ role.rank }}</td>
            </tr>
          </tbody>
        </table>

        <div class="stack">
          <div class="row">
            <span class="eyebrow" style="width: 66px">owner</span>
            <span v-for="id in access.data.value?.owners ?? []" :key="id" class="tag lamp">{{ id }}</span>
            <span v-if="!access.data.value?.owners?.length" class="faint">未配置</span>
          </div>
          <div class="row">
            <span class="eyebrow" style="width: 66px">admin</span>
            <span v-for="id in access.data.value?.admins ?? []" :key="id" class="tag">{{ id }}</span>
            <span v-if="!access.data.value?.admins?.length" class="faint">未配置</span>
          </div>
          <div class="row">
            <span class="eyebrow" style="width: 66px">member</span>
            <span v-for="id in access.data.value?.members ?? []" :key="id" class="tag">{{ id }}</span>
            <span v-if="!access.data.value?.members?.length" class="faint">未配置</span>
          </div>
        </div>

        <p class="hint" style="margin: 0">
          名单只来自服务端配置，
          <span class="mono">trust_protocol_roles={{ access.data.value?.trust_protocol_roles }}</span>。
          开启时协议端可以在消息里声明角色 —— 仅在完全可信的传输上才应开启。
        </p>
      </div>
    </section>
  </div>

  <div v-if="audit.error.value" class="error-banner">{{ audit.error.value }}</div>
</template>
