<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
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

// Machine tokens from the audit record (`authz`, `injection`, `deny`, …). Deliberately
// left untranslated: these are the values an operator greps for in the log, and a
// translated copy would make the panel and the file disagree.
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
      <span class="readout__label">{{ t('security.eventsInWindow') }}</span>
      <span class="readout__value">{{ num(counts.total) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('security.denied') }}</span>
      <span class="readout__value" style="color: var(--danger)">{{ num(counts.deny) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('security.blocked') }}</span>
      <span class="readout__value" style="color: var(--warn)">{{ num(counts.block) }}</span>
    </div>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('security.auditStream') }}</h2>
      <span class="strip__spacer" />
      <select v-model="kind" class="field" style="width: 180px" :aria-label="t('common.filterByType')">
        <option value="">{{ t('security.allKinds') }}</option>
        <option v-for="item in kinds" :key="item" :value="item">{{ item }}</option>
      </select>
    </div>
    <div class="panel__body flush">
      <div class="scroll">
        <table v-if="events.length" class="data"><caption class="visually-hidden">{{ t('security.auditStream') }}</caption>
          <thead>
            <tr>
              <th scope="col">{{ t('common.time') }}</th>
              <th scope="col">{{ t('common.type') }}</th>
              <th scope="col">{{ t('common.action') }}</th>
              <th scope="col">{{ t('common.result') }}</th>
              <th scope="col">{{ t('common.user') }}</th>
              <th scope="col">{{ t('common.role') }}</th>
              <th scope="col">{{ t('common.group') }}</th>
              <th scope="col">{{ t('common.detail') }}</th>
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
        <div v-else class="empty">{{ t('security.noEvents') }}</div>
      </div>
    </div>
  </section>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('security.floors') }}</h2>
        <span class="hint">{{ t('security.floorsHint') }}</span>
      </div>
      <div class="panel__body flush">
        <table class="data"><caption class="visually-hidden">{{ t('security.floors') }}</caption>
          <thead>
            <tr>
              <th scope="col">{{ t('security.permission') }}</th>
              <th scope="col">{{ t('security.minRole') }}</th>
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
        <h2>{{ t('security.rolesAndLists') }}</h2>
      </div>
      <div class="panel__body stack">
        <table class="data"><caption class="visually-hidden">{{ t('security.rolesAndLists') }}</caption>
          <thead>
            <tr>
              <th scope="col">{{ t('common.role') }}</th>
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
            <span v-if="!access.data.value?.owners?.length" class="faint">{{ t('common.notConfigured') }}</span>
          </div>
          <div class="row">
            <span class="eyebrow" style="width: 66px">admin</span>
            <span v-for="id in access.data.value?.admins ?? []" :key="id" class="tag">{{ id }}</span>
            <span v-if="!access.data.value?.admins?.length" class="faint">{{ t('common.notConfigured') }}</span>
          </div>
          <div class="row">
            <span class="eyebrow" style="width: 66px">member</span>
            <span v-for="id in access.data.value?.members ?? []" :key="id" class="tag">{{ id }}</span>
            <span v-if="!access.data.value?.members?.length" class="faint">{{ t('common.notConfigured') }}</span>
          </div>
        </div>

        <!-- The `key=value` reading gets its own line: it is a config value to compare
             against a file, not a word in a sentence, and splitting a sentence around
             it is what makes the old text untranslatable. -->
        <p class="hint" style="margin: 0">
          {{ t('security.allowListHint') }}
          <span class="mono" style="display: block; margin: 4px 0">
            trust_protocol_roles={{ access.data.value?.trust_protocol_roles }}
          </span>
          {{ t('security.trustWarn') }}
        </p>
      </div>
    </section>
  </div>

  <div v-if="audit.error.value" class="error-banner">{{ audit.error.value }}</div>
</template>
