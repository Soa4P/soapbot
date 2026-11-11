<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
import { copyText } from '@/lib/clipboard'
import { useAsync } from '@/lib/useAsync'

/**
 * Page 15 — archive accounts, invites, conversation grants.
 *
 * These endpoints existed before this page; until now the only way to sign an invite
 * or disable an account was a raw API call, which meant the owner's day-to-day
 * administration ran through curl while the panel pretended the feature did not
 * exist. The page is deliberately thin over the four calls: list, invite, status,
 * grant. There is no delete — the backend refuses it by design (a deleted account
 * would take its membership grants with it), so the UI must not offer one.
 */

const accounts = useAsync(() => api.accounts())

type AccountRow = { id: number; username: string; role: string; status: string }

const rows = computed<AccountRow[]>(() => accounts.data.value?.accounts ?? [])

// Labels resolve in computeds so a language switch re-renders them (the BudgetView
// import-time-array bug, documented there, applies to every page equally).
const roleLabel = (value: string): string =>
  value === 'owner' ? t('accounts.role.owner') : t('accounts.role.member')

const inviteRole = ref('member')
const inviteHours = ref(72)
const inviteMaxUses = ref(1)
const inviteSessionKeys = ref('')
const inviteResult = ref('')
const inviteError = ref('')
const inviteBusy = ref(false)
const inviteCopied = ref(false)

const grantAccountId = ref<number | ''>('')
const grantSessionKey = ref('')
const grantMessage = ref('')
const grantError = ref('')
const grantBusy = ref(false)

const statusBusyId = ref(0)
const statusError = ref('')

const webTalkKey = (accountId: number): string => `web:private:account-${accountId}`

function selectForTalk(row: AccountRow): void {
  // One click = the whole conversation grant: the session key is derived, not typed,
  // so the owner never has to know the `web:private:account-<id>` shape.
  grantAccountId.value = row.id
  grantSessionKey.value = webTalkKey(row.id)
  grantMessage.value = ''
  grantError.value = ''
}

async function submitInvite(): Promise<void> {
  inviteBusy.value = true
  inviteError.value = ''
  inviteResult.value = ''
  inviteCopied.value = false
  try {
    const keys = inviteSessionKeys.value
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean)
    const result = await api.createInvite({
      role: inviteRole.value,
      hours: inviteHours.value,
      max_uses: inviteMaxUses.value,
      session_keys: keys,
    })
    inviteResult.value = result.invite
  } catch (err) {
    inviteError.value = err instanceof Error ? err.message : t('accounts.invite.error')
  } finally {
    inviteBusy.value = false
  }
}

async function copyInvite(): Promise<void> {
  if (!inviteResult.value) return
  inviteCopied.value = await copyText(inviteResult.value)
}

async function submitGrant(): Promise<void> {
  if (grantAccountId.value === '' || !grantSessionKey.value.trim()) return
  grantBusy.value = true
  grantError.value = ''
  grantMessage.value = ''
  try {
    await api.grantMembership(grantAccountId.value, grantSessionKey.value.trim())
    grantMessage.value = t('accounts.grant.ok')
  } catch (err) {
    grantError.value = err instanceof Error ? err.message : t('accounts.grant.error')
  } finally {
    grantBusy.value = false
  }
}

async function toggleStatus(row: AccountRow): Promise<void> {
  const next = row.status === 'active' ? 'disabled' : 'active'
  statusBusyId.value = row.id
  statusError.value = ''
  try {
    await api.setAccountStatus(row.id, next)
    await accounts.reload()
  } catch (err) {
    // The backend refuses to disable the last active owner; surface that reason.
    statusError.value = err instanceof Error ? err.message : t('accounts.status.error')
  } finally {
    statusBusyId.value = 0
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('accounts.list') }}</h2>
      <span class="tag">{{ rows.length }}</span>
    </div>
    <div class="panel__body flush">
      <div class="scroll">
        <table v-if="rows.length" class="data">
          <caption class="visually-hidden">{{ t('accounts.list') }}</caption>
          <thead>
            <tr>
              <th scope="col" class="num">#</th>
              <th scope="col">{{ t('accounts.username') }}</th>
              <th scope="col">{{ t('accounts.role.title') }}</th>
              <th scope="col">{{ t('common.status') }}</th>
              <th scope="col">{{ t('accounts.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td class="num">{{ row.id }}</td>
              <td style="color: var(--ink)">{{ row.username }}</td>
              <td>
                <span class="tag" :class="row.role === 'owner' ? 'ok' : ''">
                  {{ roleLabel(row.role) }}
                </span>
              </td>
              <td>
                <span class="tag" :class="row.status === 'active' ? 'ok' : 'bad'">
                  {{ row.status === 'active' ? t('accounts.status.active') : t('accounts.status.disabled') }}
                </span>
              </td>
              <td>
                <div class="accounts__actions">
                  <button
                    type="button"
                    class="btn"
                    :disabled="statusBusyId === row.id"
                    @click="toggleStatus(row)"
                  >
                    {{
                      row.status === 'active' ? t('accounts.status.disable') : t('accounts.status.enable')
                    }}
                  </button>
                  <button type="button" class="btn" @click="selectForTalk(row)">
                    {{ t('accounts.grant.talk') }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else-if="!accounts.loading.value" class="empty">
          {{ t('accounts.empty') }}
        </div>
        <div v-else class="empty">{{ t('accounts.loading') }}</div>
      </div>
    </div>
  </section>

  <div v-if="statusError" class="error-banner">{{ statusError }}</div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('accounts.invite.title') }}</h2>
    </div>
    <div class="panel__body">
      <p class="hint" style="margin: 0 0 12px">{{ t('accounts.invite.hint') }}</p>
      <div class="accounts__form">
        <label class="accounts__field">
          <span>{{ t('accounts.role.title') }}</span>
          <select v-model="inviteRole" class="field">
            <option value="member">{{ t('accounts.role.member') }}</option>
            <option value="owner">{{ t('accounts.role.owner') }}</option>
          </select>
        </label>
        <label class="accounts__field">
          <span>{{ t('accounts.invite.hours') }}</span>
          <input v-model.number="inviteHours" class="field" type="number" min="1" max="720" />
        </label>
        <label class="accounts__field">
          <span>{{ t('accounts.invite.maxUses') }}</span>
          <input v-model.number="inviteMaxUses" class="field" type="number" min="1" max="100" />
        </label>
      </div>
      <label class="accounts__field" style="margin-top: 10px">
        <span>{{ t('accounts.invite.sessionKeys') }}</span>
        <textarea
          v-model="inviteSessionKeys"
          class="field"
          rows="2"
          :placeholder="t('accounts.invite.sessionKeysHint')"
        />
      </label>
      <div class="accounts__actions" style="margin-top: 12px">
        <button type="button" class="btn" :disabled="inviteBusy" @click="submitInvite">
          {{ inviteBusy ? t('accounts.invite.busy') : t('accounts.invite.create') }}
        </button>
      </div>
      <div v-if="inviteResult" class="accounts__code">
        <code class="mono">{{ inviteResult }}</code>
        <button type="button" class="btn" @click="copyInvite">
          {{ inviteCopied ? t('accounts.copied') : t('accounts.copy') }}
        </button>
      </div>
      <p class="hint" style="margin: 8px 0 0">{{ t('accounts.invite.once') }}</p>
      <div v-if="inviteError" class="error-banner" style="margin-top: 10px">{{ inviteError }}</div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('accounts.grant.title') }}</h2>
    </div>
    <div class="panel__body">
      <p class="hint" style="margin: 0 0 12px">{{ t('accounts.grant.hint') }}</p>
      <div class="accounts__form">
        <label class="accounts__field">
          <span>{{ t('accounts.grant.account') }}</span>
          <select v-model.number="grantAccountId" class="field">
            <option value="" disabled>{{ t('accounts.grant.pickAccount') }}</option>
            <option v-for="row in rows" :key="row.id" :value="row.id">{{ row.username }}</option>
          </select>
        </label>
        <label class="accounts__field" style="flex: 2">
          <span>{{ t('common.session') }}</span>
          <input v-model="grantSessionKey" class="field mono" type="text" spellcheck="false" />
        </label>
      </div>
      <div class="accounts__actions" style="margin-top: 12px">
        <button
          type="button"
          class="btn"
          :disabled="grantBusy || grantAccountId === '' || !grantSessionKey.trim()"
          @click="submitGrant"
        >
          {{ grantBusy ? t('accounts.grant.busy') : t('accounts.grant.submit') }}
        </button>
      </div>
      <p v-if="grantMessage" class="hint" style="margin: 8px 0 0; color: var(--ok, var(--ink))">
        {{ grantMessage }}
      </p>
      <div v-if="grantError" class="error-banner" style="margin-top: 10px">{{ grantError }}</div>
    </div>
  </section>

  <div v-if="accounts.error.value" class="error-banner">{{ accounts.error.value }}</div>
</template>

<style scoped>
.accounts__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.accounts__form {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.accounts__field {
  display: grid;
  gap: 4px;
  flex: 1;
  min-width: 140px;
  font-size: 12px;
  color: var(--ink-3);
}

.accounts__code {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius);
  background: var(--surface-2);
  overflow-wrap: anywhere;
}
</style>
