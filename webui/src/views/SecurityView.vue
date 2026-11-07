<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import EmptyState from '@/components/EmptyState.vue'
import { t } from '@/i18n'
import { datetime, num } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const kind = ref('')

/**
 * How much of the audit ring this page asks for.
 *
 * The endpoint caps at 1000 (`Query(1000)`), and the ring itself is bounded, so this is
 * a window rather than a page-through. Growing it on demand keeps the first paint cheap
 * on a busy deployment while still letting an operator widen the view during triage —
 * the alternative was a fixed 300 that silently hid the events they were looking for.
 */
const AUDIT_STEP = 300
const AUDIT_MAX = 1000
const auditLimit = ref(AUDIT_STEP)
const audit = useAsync(() => api.audit(auditLimit.value, kind.value))
const access = useAsync(() => api.access())

const canLoadMoreAudit = computed(() => auditLimit.value < AUDIT_MAX)

function loadMoreAudit(): void {
  auditLimit.value = Math.min(auditLimit.value + AUDIT_STEP, AUDIT_MAX)
}

// ``useAsync`` already reloads on the global refresh signal; only the local filter and
// the requested window need their own trigger.
watch([kind, auditLimit], () => void audit.reload())

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

// ----------------------------------------------------------------- 授权名单编辑
//
// The lists were read-only here while the real edit path was "ssh in, edit .env, restart".
// A panel that displays who holds power but cannot change it is a report, not a control.
//
// Draft-first: every edit lands in `draft`, and 保存 is the only thing that talks to the
// server — same read → review → write discipline the other config pages use.
const draft = ref<{ owners: string[]; admins: string[]; members: string[] }>({
  owners: [],
  admins: [],
  members: [],
})
const dirty = ref(false)
const addRole = ref<'owner' | 'admin' | 'member'>('admin')
const addId = ref('')
const authorityBusy = ref(false)
const authorityNote = ref('')
const authorityError = ref('')
//: The command the server says restarts *this* deployment. Rendered verbatim: a
//: hard-coded one named the wrong Windows task and made a successful save look broken.
const restartHint = ref('')

//: Saved lists only reach the running process after it restarts, and the panel reads
//: its own copy at startup. So the panel asks for a restart and then watches the
//: health endpoint; without this the operator sees the old list and concludes that
//: nothing was saved.
type RestartState = 'idle' | 'restarting' | 'done' | 'failed'
const restartState = ref<RestartState>('idle')
let restartAborted = false

onUnmounted(() => {
  restartAborted = true
})

async function waitForRestart(): Promise<void> {
  const deadline = Date.now() + 60_000
  while (!restartAborted && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 2_000))
    if (restartAborted) return
    try {
      const response = await fetch('/api/health', { cache: 'no-store' })
      if (response.ok) {
        restartState.value = 'done'
        await access.reload()
        return
      }
    } catch {
      // degraded: the server is still down, keep polling until the deadline
    }
  }
  if (!restartAborted) restartState.value = 'failed'
}

function seedDraft(): void {
  draft.value = {
    owners: [...(access.data.value?.owners ?? [])],
    admins: [...(access.data.value?.admins ?? [])],
    members: [...(access.data.value?.members ?? [])],
  }
  dirty.value = false
}
watch(access.data, () => {
  if (!dirty.value) seedDraft()
})

/** The server refuses a write that would leave zero owners; catching it here too means the
 * button explains itself instead of the operator discovering the rule from a 400. */
const noOwnerLeft = computed(() => draft.value.owners.length === 0)

function addEntry(): boolean {
  const raw = addId.value.trim()
  if (!raw) return false
  // Digits-only pre-check so a paste with spaces/labels is normalised, but a non-number
  // is refused in place rather than stored and rejected by the server later.
  const id = String(raw).replace(/[＋+]/g, '').replace(/\D/g, '')
  if (!id) {
    authorityError.value = t('security.qqInvalid')
    return false
  }
  authorityError.value = ''
  // One account, one role. Permission resolution takes the highest rank, so adding the
  // same number to a second list changes nothing except to make the page lie: it would
  // show "member" for someone the runtime still treats as owner, and removing them from
  // that list would appear to do nothing.
  const other = (['owner', 'admin', 'member'] as const).find(
    (role) => role !== addRole.value && draft.value[roleKey[role]].includes(id),
  )
  if (other) {
    authorityError.value = t('security.roleConflictAdd', {
      id,
      role: other,
    })
    return false
  }
  const list = draft.value[roleKey[addRole.value]]
  if (!list.includes(id)) list.push(id)
  addId.value = ''
  dirty.value = true
  return true
}

/** Every QQ that appears in more than one list, with the roles it holds. */
const conflicts = computed(() => {
  const seen = new Map<string, string[]>()
  const add = (qq: string, role: string) => {
    seen.set(qq, [...(seen.get(qq) ?? []), role])
  }
  draft.value.owners.forEach((qq) => add(qq, 'owner'))
  draft.value.admins.forEach((qq) => add(qq, 'admin'))
  draft.value.members.forEach((qq) => add(qq, 'member'))
  return [...seen.entries()].filter(([, roles]) => roles.length > 1)
})

/** Role names are singular; the list keys (and the API fields) are plural. */
const roleKey = {
  owner: 'owners',
  admin: 'admins',
  member: 'members',
} as const

function removeEntry(role: 'owner' | 'admin' | 'member', id: string): void {
  const key = roleKey[role]
  draft.value[key] = draft.value[key].filter((x) => x !== id)
  dirty.value = true
}

async function saveAuthority(): Promise<void> {
  // A number typed into the box but never "added" is exactly the state an operator
  // believes is saved. Commit it first; leaving the button disabled with no message
  // is what made the page look broken.
  if (addId.value.trim()) addEntry()
  if (!dirty.value && !noOwnerLeft.value && !conflicts.value.length) {
    authorityNote.value = t('security.nothingToSave')
    return
  }
  if (noOwnerLeft.value) {
    authorityError.value = t('security.lastOwnerGuard')
    return
  }
  if (conflicts.value.length) {
    // The server refuses this too; saying it here means the person sees which number
    // and which roles before a failed round trip.
    authorityError.value = t('security.roleConflictSave', {
      detail: conflicts.value.map(([qq, roles]) => `${qq}(${roles.join('/')})`).join(', '),
    })
    return
  }
  authorityBusy.value = true
  authorityError.value = ''
  try {
    const body = await api.writeAuthority({
      owners: draft.value.owners,
      admins: draft.value.admins,
      members: draft.value.members,
    })
    draft.value = { owners: body.owners, admins: body.admins, members: body.members }
    dirty.value = false
    authorityNote.value = t('security.authoritySaved')
    restartHint.value = String(body.restart_hint || '')
    restartState.value = 'restarting'
    try {
      await api.restartService()
    } catch {
      // ignored: the process may exit before the response lands, and the health poll
      // decides whether it came back. Surfacing it would report an error on success.
    }
    void waitForRestart()
  } catch (error) {
    authorityError.value = (error as Error).message
  } finally {
    authorityBusy.value = false
  }
}

// ------------------------------------------------------------------ 令牌生命周期
//
// A signed token used to be valid for its whole ttl whatever happened to it. This panel
// is the operator's only way to see that a credential *was* killed, and to kill all of
// them when a device is lost — without rotating the signing secret, which logs everyone
// out and therefore never gets used.
const revocations = useAsync(() => api.revocations())
const tokenBusy = ref(false)
const tokenNote = ref('')
const tokenError = ref('')

const revokedTokens = computed<any[]>(() => revocations.data.value?.tokens ?? [])
const revokedBefore = computed(() => Number(revocations.data.value?.revoked_before ?? 0))

async function revokeEveryToken(): Promise<void> {
  tokenBusy.value = true
  tokenNote.value = ''
  tokenError.value = ''
  try {
    await api.revokeAllTokens()
    // The server rotates the session cookie in the same response. Dropping the
    // replacement in the client would lock the operator out: the bootstrap token
    // was consumed at first login and cannot be reused.
    tokenNote.value = t('security.tokensRevoked')
    await revocations.reload()
    await auth.refresh()
  } catch (error) {
    tokenError.value = (error as Error).message
  } finally {
    tokenBusy.value = false
  }
}
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
      <h2>{{ t('security.tokens') }}</h2>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" :disabled="tokenBusy" @click="revokeEveryToken">
        {{ tokenBusy ? t('common.working') : t('security.revokeAll') }}
      </button>
    </div>
    <div class="panel__body stack">
      <p class="hint">{{ t('security.tokensHint') }}</p>
      <p v-if="revokedBefore" class="hint">
        {{ t('security.revokedBefore', { when: datetime(revokedBefore) }) }}
      </p>
      <p v-if="tokenNote" class="hint" role="status">{{ tokenNote }}</p>
      <p v-if="tokenError" class="hint" role="alert" style="color: var(--danger)">
        {{ tokenError }}
      </p>
      <table v-if="revokedTokens.length" class="data">
        <caption class="visually-hidden">{{ t('security.tokens') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('security.tokenId') }}</th>
            <th scope="col">{{ t('security.expires') }}</th>
            <th scope="col">{{ t('security.state') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in revokedTokens" :key="item.jti">
            <td class="key mono">{{ item.jti }}</td>
            <td>{{ datetime(item.expires_at) }}</td>
            <td>
              <span class="tag" :class="item.expired ? '' : 'bad'">
                {{ item.expired ? t('security.expired') : t('security.revoked') }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="hint">{{ t('security.noRevoked') }}</p>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('security.auditStream') }}</h2>
      <span class="strip__spacer" />
      <select v-model="kind" class="field" style="width: 180px" :aria-label="t('common.filterByType')">
        <option value="">{{ t('security.allKinds') }}</option>
        <option v-for="item in kinds" :key="item" :value="item">{{ item }}</option>
      </select>
      <button
        v-if="canLoadMoreAudit && events.length"
        class="btn ghost"
        type="button"
        :disabled="audit.loading.value"
        @click="loadMoreAudit"
      >
        {{ t('common.loadMore') }}
      </button>
    </div>
    <!-- The page used to be a table with no explanation of what gets recorded. Answering
         "what counts as an event" on the page itself is cheaper than making someone read
         the source to find out. -->
    <details class="audit-help">
      <summary>{{ t('security.auditWhat') }}</summary>
      <p class="hint" style="margin: 6px 0 0">{{ t('security.auditWhatBody') }}</p>
      <p class="hint" style="margin: 4px 0 0">{{ t('security.auditKinds') }}</p>
    </details>
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
        <EmptyState
          v-else
          :lead="t('security.noEvents')"
          :hint="t('security.noEventsHint')"
          to="/settings"
          :action="t('security.noEventsAction')"
        />
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
          <div v-for="role in (['owner', 'admin', 'member'] as const)" :key="role" class="row">
            <span class="eyebrow" style="width: 66px">{{ role }}</span>
            <span
              v-for="id in draft[roleKey[role]]"
              :key="`${role}-${id}`"
              class="tag"
              :class="role === 'owner' ? 'lamp' : ''"
            >
              {{ id }}
              <button
                v-if="auth.canEditAuthority"
                class="tag__remove"
                type="button"
                :aria-label="t('security.removeAria', { id, role })"
                @click="removeEntry(role, id)"
              >
                ×
              </button>
            </span>
            <span v-if="!draft[roleKey[role]].length" class="faint">
              {{ t('common.notConfigured') }}
            </span>
          </div>
        </div>

        <!-- The edit affordance lives next to the list it edits: a separate "权限管理"
             page would separate the decision from the state it changes. Everyone can
             read the lists; only admin and above get the controls, because a form that
             always answers 403 looks broken rather than forbidden. -->
        <div v-if="auth.canEditAuthority" class="row" style="flex-wrap: wrap; gap: 8px">
          <select v-model="addRole" class="field" style="width: 110px" :aria-label="t('security.roleAria')">
            <option value="owner">owner</option>
            <option value="admin">admin</option>
            <option value="member">member</option>
          </select>
          <input
            v-model="addId"
            class="field"
            style="width: 200px"
            inputmode="numeric"
            :placeholder="t('security.qqPlaceholder')"
            :aria-label="t('security.qqAria')"
            @keydown.enter.prevent="addEntry"
          />
          <button class="btn ghost" type="button" @click="addEntry">
            {{ t('security.add') }}
          </button>
          <span class="strip__spacer" />
          <button
            class="btn"
            type="button"
            :disabled="authorityBusy || conflicts.length > 0"
            @click="saveAuthority"
          >
            {{ authorityBusy ? t('security.saving') : t('security.save') }}
          </button>
        </div>
        <p v-else class="hint" style="margin: 0">
          {{ t('security.authorityReadOnly', { role: auth.role }) }}
        </p>
        <p v-if="authorityNote" class="hint" style="margin: 0; color: var(--ok)">
          {{ authorityNote }}
          <span v-if="restartHint" class="mono" style="display: block; margin-top: 4px">
            {{ restartHint }}
          </span>
        </p>
        <p
          v-if="restartState !== 'idle'"
          class="hint"
          role="status"
          :style="{
            margin: 0,
            color: restartState === 'failed' ? 'var(--danger)' : 'var(--ink-2)',
          }"
        >
          <span v-if="restartState === 'restarting'">{{ t('security.restarting') }}</span>
          <span v-else-if="restartState === 'done'">{{ t('security.restartDone') }}</span>
          <span v-else>{{ t('security.restartFailed') }}</span>
        </p>
        <p v-if="authorityError" class="hint" style="margin: 0; color: var(--danger)">
          {{ authorityError }}
        </p>
        <p class="hint" style="margin: 0">{{ t('security.authorityHint') }}</p>

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
