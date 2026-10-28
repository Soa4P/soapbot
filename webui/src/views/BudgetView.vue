<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
import { datetime, money, num, untilFuture } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const status = ref('')
const budget = useAsync(() => api.budget({ status: status.value, limit: 200 }))

watch(status, () => void budget.reload())

const enabled = computed(() => Boolean(budget.data.value?.enabled))
const policy = computed<any>(() => budget.data.value?.policy ?? {})
const requests = computed<any[]>(() => budget.data.value?.requests ?? [])

const totals = computed(() => {
  let pending = 0
  let approved = 0
  for (const row of requests.value) {
    if (row.status === 'pending' || row.status === 'reserved') pending += row.amount_minor
    if (row.status === 'approved') approved += row.amount_minor
  }
  return { pending, approved }
})

const statuses = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已批准' },
  { value: 'denied', label: '已驳回' },
  { value: 'expired', label: '已过期' },
  { value: 'cancelled', label: '已取消' },
]

function statusLabel(value: string): string {
  return statuses.find((s) => s.value === value)?.label ?? value
}

function statusClass(value: string): string {
  if (value === 'pending' || value === 'reserved') return 'lamp'
  if (value === 'approved') return 'ok'
  if (value === 'denied') return 'bad'
  return ''
}
</script>

<template>
  <div v-if="!enabled" class="warn-banner">
    额度管理未启用。启用后 <span class="mono">/budget</span> 才会出现在命令列表里。
    设置 <span class="mono">SOAPBOT_ENABLE_BUDGET=true</span>（需要已配置记忆存储）后重启。
  </div>

  <div class="grid cols-4">
    <div class="readout">
      <span class="readout__label">本期上限</span>
      <span class="readout__value">{{ money(policy.period_cap_minor, policy.currency) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">单笔上限</span>
      <span class="readout__value">{{ money(policy.per_request_cap_minor, policy.currency) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">待批金额（列表内）</span>
      <span class="readout__value" style="color: var(--brand)">
        {{ money(totals.pending, policy.currency) }}
      </span>
    </div>
    <div class="readout">
      <span class="readout__label">已批准（列表内）</span>
      <span class="readout__value">{{ money(totals.approved, policy.currency) }}</span>
    </div>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>消费申请</h2>
      <span class="tag">{{ requests.length }}</span>
      <span class="strip__spacer" />
      <select v-model="status" class="field" style="width: 150px" aria-label="按状态过滤">
        <option v-for="item in statuses" :key="item.value" :value="item.value">
          {{ item.label }}
        </option>
      </select>
    </div>
    <div class="panel__body flush">
      <div class="scroll">
        <table v-if="requests.length" class="data"><caption class="visually-hidden">消费申请</caption>
          <thead>
            <tr>
              <th scope="col" class="num">#</th>
              <th scope="col" class="num">金额</th>
              <th scope="col">用途</th>
              <th scope="col">申请者</th>
              <th scope="col">会话</th>
              <th scope="col">状态</th>
              <th scope="col">创建</th>
              <th scope="col">处理</th>
              <th scope="col">备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in requests" :key="row.id">
              <td class="num">{{ row.id }}</td>
              <td class="num" style="color: var(--ink)">
                {{ money(row.amount_minor, row.currency) }}
              </td>
              <td class="key" style="max-width: 220px">{{ row.purpose || '（未填）' }}</td>
              <td>{{ row.requester_name || row.requester_id || '—' }}</td>
              <td style="max-width: 200px">{{ row.session_key }}</td>
              <td>
                <span class="tag" :class="statusClass(row.status)">{{ statusLabel(row.status) }}</span>
              </td>
              <td style="white-space: nowrap">{{ datetime(row.created_at) }}</td>
              <td style="white-space: nowrap">
                <template v-if="row.decided_at">
                  {{ datetime(row.decided_at) }}
                  <span class="faint">/ {{ row.decided_by || '—' }}</span>
                </template>
                <span v-else class="faint">{{ untilFuture(row.expires_at) }}过期</span>
              </td>
              <td style="max-width: 220px">{{ row.decision_note || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">
          {{ enabled ? '没有符合条件的申请。' : '额度管理未启用。' }}
        </div>
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>策略</h2>
    </div>
    <div class="panel__body">
      <table class="data" aria-label="策略">
        <tbody>
          <tr>
            <th scope="row">币种</th>
            <td class="key">{{ policy.currency || '—' }}</td>
          </tr>
          <tr>
            <th scope="row">周期</th>
            <td class="key">{{ policy.period || '—' }} · 本期 {{ policy.period_key || '—' }}</td>
          </tr>
          <tr>
            <th scope="row">申请有效期</th>
            <td class="key">{{ num(policy.request_ttl_seconds) }} 秒</td>
          </tr>
        </tbody>
      </table>
      <p class="hint" style="margin: 12px 0 0">
        金额一律按最小货币单位（分）记账，避免浮点漂移。批准需要
        <span class="mono">APPROVE_PAYMENT</span>（仅 owner），且不能批准自己发起的申请。
        本机器人不执行任何支付动作。
      </p>
    </div>
  </section>

  <div v-if="budget.error.value" class="error-banner">{{ budget.error.value }}</div>
</template>
