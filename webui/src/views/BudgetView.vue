<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
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

/**
 * Labels are resolved inside a computed, not in a module-level array.
 *
 * A plain `const statuses = [{ label: t('...') }]` is evaluated once at import, so the
 * dropdown would keep the language it happened to load in while the rest of the page
 * switched. The bug is invisible in a screenshot and obvious to the person who flips
 * the switch, which is the wrong way round.
 */
const statuses = computed(() => [
  { value: '', label: t('common.all') },
  { value: 'pending', label: t('budget.status.pending') },
  { value: 'approved', label: t('budget.status.approved') },
  { value: 'denied', label: t('budget.status.denied') },
  { value: 'expired', label: t('budget.status.expired') },
  { value: 'cancelled', label: t('budget.status.cancelled') },
])

function statusLabel(value: string): string {
  return statuses.value.find((s) => s.value === value)?.label ?? value
}

function statusClass(value: string): string {
  if (value === 'pending' || value === 'reserved') return 'lamp'
  if (value === 'approved') return 'ok'
  if (value === 'denied') return 'bad'
  return ''
}
</script>

<template>
  <!-- The env var is lifted onto its own line rather than left mid-sentence. It is the
       one thing the operator has to act on, and a value buried in prose is scrolled
       past; it also lets the sentence itself stay one translatable unit. -->
  <div v-if="!enabled" class="warn-banner">
    <strong>{{ t('budget.disabledTitle') }}</strong>
    <div class="mono" style="margin: 4px 0">SOAPBOT_ENABLE_BUDGET=true</div>
    {{ t('budget.disabledHint') }}
  </div>

  <div class="grid cols-4">
    <div class="readout">
      <span class="readout__label">{{ t('budget.cap.period') }}</span>
      <span class="readout__value">{{ money(policy.period_cap_minor, policy.currency) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('budget.cap.request') }}</span>
      <span class="readout__value">{{ money(policy.per_request_cap_minor, policy.currency) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('budget.pendingInList') }}</span>
      <span class="readout__value" style="color: var(--brand)">
        {{ money(totals.pending, policy.currency) }}
      </span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('budget.approvedInList') }}</span>
      <span class="readout__value">{{ money(totals.approved, policy.currency) }}</span>
    </div>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('budget.requests') }}</h2>
      <span class="tag">{{ requests.length }}</span>
      <span class="strip__spacer" />
      <select v-model="status" class="field" style="width: 150px" :aria-label="t('common.filterByStatus')">
        <option v-for="item in statuses" :key="item.value" :value="item.value">
          {{ item.label }}
        </option>
      </select>
    </div>
    <div class="panel__body flush">
      <div class="scroll">
        <table v-if="requests.length" class="data"><caption class="visually-hidden">{{ t('budget.requests') }}</caption>
          <thead>
            <tr>
              <th scope="col" class="num">#</th>
              <th scope="col" class="num">{{ t('budget.amount') }}</th>
              <th scope="col">{{ t('budget.purpose') }}</th>
              <th scope="col">{{ t('budget.requester') }}</th>
              <th scope="col">{{ t('common.session') }}</th>
              <th scope="col">{{ t('common.status') }}</th>
              <th scope="col">{{ t('budget.created') }}</th>
              <th scope="col">{{ t('budget.decided') }}</th>
              <th scope="col">{{ t('budget.note') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in requests" :key="row.id">
              <td class="num">{{ row.id }}</td>
              <td class="num" style="color: var(--ink)">
                {{ money(row.amount_minor, row.currency) }}
              </td>
              <td class="key" style="max-width: 220px">{{ row.purpose || t('budget.blankPurpose') }}</td>
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
                <span v-else class="faint">{{ t('budget.expiresIn', { when: untilFuture(row.expires_at) }) }}</span>
              </td>
              <td style="max-width: 220px">{{ row.decision_note || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">
          {{ enabled ? t('budget.emptyFiltered') : t('budget.emptyDisabled') }}
        </div>
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('budget.policy') }}</h2>
    </div>
    <div class="panel__body">
      <table class="data" :aria-label="t('budget.policy')">
        <tbody>
          <tr>
            <th scope="row">{{ t('budget.currency') }}</th>
            <td class="key">{{ policy.currency || '—' }}</td>
          </tr>
          <tr>
            <th scope="row">{{ t('budget.period') }}</th>
            <td class="key">
              {{ policy.period || '—' }}{{ t('budget.periodCurrent', { key: policy.period_key || '—' }) }}
            </td>
          </tr>
          <tr>
            <th scope="row">{{ t('budget.ttl') }}</th>
            <td class="key">{{ t('common.seconds', { n: num(policy.request_ttl_seconds) }) }}</td>
          </tr>
        </tbody>
      </table>
      <p class="hint" style="margin: 12px 0 0">
        {{ t('budget.note.money') }}
        {{ t('budget.note.approveLead') }}
        <span class="mono">APPROVE_PAYMENT</span>{{ t('budget.note.approveTail') }}
      </p>
    </div>
  </section>

  <div v-if="budget.error.value" class="error-banner">{{ budget.error.value }}</div>
</template>
