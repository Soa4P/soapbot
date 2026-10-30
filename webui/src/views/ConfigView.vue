<script setup lang="ts">
import { computed, ref } from 'vue'

import { api, type DiffResult, type ProviderEntry, type ProvidersDocument, type ProvidersPatch } from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DiffEditor from '@/components/DiffEditor.vue'
import McpServers from '@/components/McpServers.vue'
import { t } from '@/i18n'
import { num, truncate } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

/**
 * 07 — providers and personas.
 *
 * This page was read-only by design, and the reasoning was that identity and failover
 * target are configuration which belongs in a reviewed file. That reasoning still holds;
 * what changed is where the review happens. Editing here goes through three steps —
 * read, diff, apply — so the operator sees the exact lines that will change and confirms
 * them, and the change is written to the audit log. A file edited over SSH had neither.
 *
 * The personas section stays read-only in this pass. Persona cards are Markdown with
 * front matter, and a form that renders them as fields would silently drop the prose
 * between the front matter and the body — a worse outcome than leaving the section
 * informative but not editable.
 */
const providers = useAsync(() => api.providers())
const personas = useAsync(() => api.personas())

const providerRows = computed<any[]>(() => providers.data.value?.providers ?? [])
const stats = computed<Record<string, any>>(() => providers.data.value?.stats ?? {})
const personaRows = computed<any[]>(() => personas.data.value?.personas ?? [])
const binding = computed<any>(() => personas.data.value?.binding ?? {})

const expanded = ref('')
function toggle(id: string): void {
  expanded.value = expanded.value === id ? '' : id
}

function statFor(id: string): any {
  return stats.value[id] ?? {}
}

/* ------------------------------------------------------------- write flow */

const document = ref<ProvidersDocument | null>(null)
const drafts = ref<ProviderEntry[]>([])
const baseHash = ref('')
const edited = ref<Record<string, boolean>>({})
const loadError = ref('')
const flowError = ref('')
const busy = ref(false)

const diff = ref<DiffResult | null>(null)
const showDiff = ref(false)
const restartNeeded = ref(false)
const appliedFields = ref<string[]>([])

const hasEdits = computed(() => Object.values(edited.value).some(Boolean))

const mask = computed(() => document.value?.mask ?? '********')
const sentinel = computed(() => document.value?.unchanged_sentinel ?? '__UNCHANGED__')

async function loadForEdit(): Promise<void> {
  busy.value = true
  loadError.value = ''
  try {
    const body = await api.configProviders()
    document.value = body
    baseHash.value = body.base_hash
    // Deep copy: the draft must be independent of `document`, or a rejected diff
    // leaves the "current" view showing edits that were never written.
    drafts.value = JSON.parse(JSON.stringify(body.document.providers ?? []))
    edited.value = {}
    diff.value = null
    showDiff.value = false
  } catch (err) {
    // Parse failures arrive here as 422 with the YAML error. Showing an empty form
    // instead would invite the operator to "save" over a file that merely had a typo.
    loadError.value = (err as Error).message
  } finally {
    busy.value = false
  }
}

function markEdited(id: string): void {
  edited.value = { ...edited.value, [id]: true }
}

function onSecretInput(row: ProviderEntry, event: Event): void {
  const value = (event.target as HTMLInputElement).value
  row.api_key = value
  markEdited(row.id)
}

function addRow(): void {
  const id = `provider-${drafts.value.length + 1}`
  drafts.value.push({
    id,
    kind: 'openai_compat',
    base_url: '',
    api_key: sentinel.value,
    model: '',
    priority: (drafts.value.length + 1) * 10,
    enabled: true,
  })
  markEdited(id)
}

function removeRow(index: number): void {
  // Deleting a provider is not supported by the patch protocol on purpose: the apply
  // endpoint merges, so a row dropped from the payload would survive. Saying so is
  // better than a button that appears to work and does nothing.
  flowError.value = t('config.removeUnsupported')
  drafts.value.splice(index, 1)
}

function payload(): ProvidersPatch {
  return {
    base_hash: baseHash.value,
    // Only edited rows are sent. Every field is included for those rows so a cleared
    // field actually clears; untouched rows are omitted so they cannot be clobbered by
    // a field the form does not render.
    providers: drafts.value
      .filter((row) => edited.value[row.id])
      .map((row) => ({ ...row, id: row.id ?? '' })),
  }
}

async function previewDiff(): Promise<void> {
  if (!hasEdits.value) {
    flowError.value = t('config.noEditsYet')
    return
  }
  busy.value = true
  flowError.value = ''
  try {
    const body = await api.configProvidersDiff(payload())
    diff.value = body
    showDiff.value = true
  } catch (err) {
    flowError.value = (err as Error).message
  } finally {
    busy.value = false
  }
}

const confirmOpen = ref(false)

function requestApply(): void {
  confirmOpen.value = true
}

async function applyChanges(): Promise<void> {
  if (!diff.value) return
  busy.value = true
  flowError.value = ''
  try {
    const body = await api.configProvidersApply({
      ...payload(),
      approved_hash: diff.value.new_hash,
    })
    if (!body.written) {
      flowError.value = t('config.notWritten', { reason: body.reason ?? t('config.noChange') })
      return
    }
    appliedFields.value = body.changed_fields
    restartNeeded.value = body.restart_required === true
    confirmOpen.value = false
    showDiff.value = false
    diff.value = null
    edited.value = {}
    await loadForEdit()
    providers.reload()
  } catch (err) {
    flowError.value = (err as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="grid cols-3">
    <div class="readout">
      <span class="readout__label">Provider</span>
      <span class="readout__value">{{ num(providerRows.length) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('overview.personas') }}</span>
      <span class="readout__value">{{ num(personaRows.length) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('config.defaultPersona') }}</span>
      <span class="readout__value" style="font-size: 15px">
        {{ binding.global_default || t('config.unset') }}
      </span>
    </div>
  </div>

  <!-- One sentence. The old version split it around a <strong>, which reads fine in
       Chinese and cannot be reordered in any other language; the banner is already the
       emphatic element on the page, so nothing is lost. -->
  <div v-if="restartNeeded" class="warn-banner" role="status">
    {{ t('config.restartBanner', { n: appliedFields.length }) }}
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('config.chain') }}</h2>
      <span class="hint">{{ t('config.chainHint') }}</span>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" :disabled="busy" @click="loadForEdit">
        {{ document ? t('config.reload') : t('config.loadToEdit') }}
      </button>
    </div>

    <div class="panel__body flush">
      <!-- read-only view when nothing has been loaded for editing -->
      <template v-if="!document">
        <table v-if="providerRows.length" class="data">
          <caption class="visually-hidden">{{ t('config.chain') }}</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">{{ t('common.type') }}</th>
              <th scope="col">{{ t('common.model') }}</th>
              <th scope="col">{{ t('common.capability') }}</th>
              <th scope="col" class="num">{{ t('overview.priority') }}</th>
              <th scope="col">{{ t('common.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in providerRows" :key="row.id">
              <td class="key">{{ row.id }}</td>
              <td>{{ row.kind }}</td>
              <td>{{ row.model || '—' }}</td>
              <td>
                <span v-for="slot in row.slots" :key="slot" class="tag" style="margin-right: 4px">
                  {{ slot }}
                </span>
              </td>
              <td class="num">{{ row.priority }}</td>
              <td>
                <span class="tag" :class="row.enabled ? 'ok' : 'bad'">
                  {{ row.enabled ? t('config.enabled') : t('config.disabled') }}
                </span>
                <span v-if="statFor(row.id).failures" class="tag bad" style="margin-left: 4px">
                  {{ t('config.failures', { n: statFor(row.id).failures }) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">
          {{ t('config.noProviders') }}
        </div>
      </template>

      <!-- editable view -->
      <div v-else class="edit">
        <p class="hint" style="margin: 0 0 8px">
          {{ t('config.secretHint', { mask }) }}
        </p>

        <table class="data">
          <caption class="visually-hidden">{{ t('config.editCaption') }}</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">{{ t('common.type') }}</th>
              <th scope="col">Base URL</th>
              <th scope="col">{{ t('common.model') }}</th>
              <th scope="col">API Key</th>
              <th scope="col" class="num">{{ t('overview.priority') }}</th>
              <th scope="col">{{ t('config.enabled') }}</th>
              <th scope="col"><span class="visually-hidden">{{ t('common.actions') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in drafts" :key="row.id" :class="{ 'edit__row--dirty': edited[row.id] }">
              <th scope="row">
                <input
                  v-model="row.id"
                  class="field"
                  style="min-width: 96px"
                  aria-label="Provider ID"
                  @input="markEdited(row.id)"
                />
              </th>
              <td>
                <input
                  v-model="row.kind"
                  class="field"
                  style="min-width: 120px"
                  :aria-label="t('common.type')"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <input
                  v-model="row.base_url"
                  class="field"
                  style="min-width: 180px"
                  aria-label="Base URL"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <input
                  v-model="row.model"
                  class="field"
                  style="min-width: 120px"
                  :aria-label="t('common.model')"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <!-- type="text" not "password": the value shown is already a mask or an
                     env: reference, and hiding it would stop the operator from seeing
                     which variable this provider is wired to. -->
                <input
                  class="field"
                  style="min-width: 140px"
                  :value="row.api_key"
                  aria-label="API Key"
                  spellcheck="false"
                  @input="onSecretInput(row, $event)"
                />
              </td>
              <td class="num">
                <input
                  v-model.number="row.priority"
                  class="field"
                  style="width: 64px; text-align: right"
                  type="number"
                  :aria-label="t('overview.priority')"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <input
                  v-model="row.enabled"
                  type="checkbox"
                  :aria-label="t('config.enableFor', { id: row.id })"
                  @change="markEdited(row.id)"
                />
              </td>
              <td>
                <button class="btn ghost" type="button" @click="removeRow(index)">{{ t('config.remove') }}</button>
              </td>
            </tr>
          </tbody>
        </table>

        <div class="row" style="margin-top: 10px">
          <button class="btn ghost" type="button" @click="addRow">{{ t('config.addProvider') }}</button>
          <span class="strip__spacer" />
          <span class="hint">{{ hasEdits ? t('config.dirty') : t('config.clean') }}</span>
          <button class="btn lamp" type="button" :disabled="busy || !hasEdits" @click="previewDiff">
            {{ busy ? t('config.computing') : t('config.previewDiff') }}
          </button>
        </div>

        <p v-if="loadError" class="error-banner" style="margin-top: 8px" role="alert">
          {{ loadError }}
        </p>
        <p v-if="flowError" class="error-banner" style="margin-top: 8px" role="alert">
          {{ flowError }}
        </p>
      </div>
    </div>
  </section>

  <section v-if="showDiff && diff" class="panel">
    <div class="panel__head">
      <h2>{{ t('config.pendingChanges') }}</h2>
      <span class="tag">{{ t('config.fieldsCount', { n: diff.changed_fields.length }) }}</span>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" @click="showDiff = false">{{ t('common.cancel') }}</button>
      <button class="btn lamp" type="button" :disabled="busy || diff.empty" @click="requestApply">
        {{ t('config.confirmWrite') }}
      </button>
    </div>
    <div class="panel__body">
      <p class="warn-banner" style="margin: 0 0 10px">
        {{ t('config.diffWarn', { path: document?.path ?? '' }) }}
      </p>
      <DiffEditor :diff="diff.diff" filename="providers.yaml" />
      <div class="hint" style="margin-top: 8px">
        {{ t('config.changedFields', {
          names: diff.changed_fields.join(t('common.listSep')) || t('config.noneFields'),
        }) }}
      </div>
    </div>
  </section>

  <!-- After providers: the same three-step write flow, different rules. -->
  <McpServers />

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('overview.personas') }}</h2>
      <span class="hint">{{ t('config.personaHint') }}</span>
    </div>
    <div class="panel__body flush">
      <div v-if="!personaRows.length" class="empty">
        {{ t('config.noPersonas') }}
      </div>
      <div v-else class="scroll">
        <table class="data">
          <caption class="visually-hidden">{{ t('overview.personas') }}</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">{{ t('common.name') }}</th>
              <th scope="col">{{ t('config.style') }}</th>
              <th scope="col">{{ t('config.wakeWords') }}</th>
              <th scope="col" class="num">{{ t('config.maxChars') }}</th>
              <th scope="col" class="num">{{ t('config.temperature') }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in personaRows" :key="row.id">
              <tr style="cursor: pointer" @click="toggle(row.id)">
                <th scope="row">
                  {{ row.id }}
                  <span v-if="!row.enabled" class="tag bad" style="margin-left: 6px">{{ t('config.disabled') }}</span>
                </th>
                <td>{{ row.name }}</td>
                <td>{{ row.style || '—' }}</td>
                <td>{{ row.wake_words.join(' / ') || '—' }}</td>
                <td class="num">{{ row.max_reply_chars || t('config.default') }}</td>
                <td class="num">{{ row.temperature ?? t('config.default') }}</td>
              </tr>
              <tr v-if="expanded === row.id">
                <td colspan="6" style="background: var(--surface-3)">
                  <div class="hint" style="margin-bottom: 6px">
                    {{ row.system_prompt_truncated
                      ? t('config.systemPromptTruncated')
                      : t('config.systemPrompt') }}
                  </div>
                  <pre
                    style="
                      white-space: pre-wrap;
                      font-size: 12px;
                      line-height: 1.6;
                      margin: 0;
                      max-height: 320px;
                      overflow: auto;
                    "
                    >{{ row.system_prompt || t('config.emptyPrompt') }}</pre
                  >
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('config.bindings') }}</h2>
      <span class="hint">{{ t('config.bindingsHint') }}</span>
    </div>
    <div class="panel__body">
      <div class="grid cols-2">
        <div>
          <div class="hint" style="margin-bottom: 6px">{{ t('config.groupBindings') }}</div>
          <table v-if="Object.keys(binding.groups ?? {}).length" class="data">
            <caption class="visually-hidden">{{ t('config.groupBindings') }}</caption>
            <thead>
              <tr>
                <th scope="col">{{ t('config.groupId') }}</th>
                <th scope="col">{{ t('config.persona') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(pid, gid) in binding.groups" :key="gid">
                <th scope="row">{{ gid }}</th>
                <td>{{ pid }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">{{ t('config.noGroupBindings') }}</div>
        </div>
        <div>
          <div class="hint" style="margin-bottom: 6px">{{ t('config.userBindings') }}</div>
          <table v-if="Object.keys(binding.users ?? {}).length" class="data">
            <caption class="visually-hidden">{{ t('config.userBindings') }}</caption>
            <thead>
              <tr>
                <th scope="col">{{ t('common.user') }}</th>
                <th scope="col">{{ t('config.persona') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(pid, uid) in binding.users" :key="uid">
                <th scope="row">{{ truncate(String(uid), 20) }}</th>
                <td>{{ pid }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">{{ t('config.noUserBindings') }}</div>
        </div>
      </div>
    </div>
  </section>

  <div v-if="providers.error.value" class="error-banner">{{ providers.error.value }}</div>
  <div v-if="personas.error.value" class="error-banner">{{ personas.error.value }}</div>

  <ConfirmDialog
    :open="confirmOpen"
    :title="t('config.confirmTitle')"
    :detail="t('config.confirmDetail', { n: diff?.changed_fields.length ?? 0 })"
    :confirm-label="t('config.write')"
    :busy="busy"
    @confirm="applyChanges"
    @cancel="confirmOpen = false"
  />
</template>

<style scoped>
.edit {
  padding: 12px;
}

.edit__row--dirty th,
.edit__row--dirty td {
  background: var(--warn-soft);
}
</style>
