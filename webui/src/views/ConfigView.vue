<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  api,
  type DiffResult,
  type ProbeResult,
  type ProviderEntry,
  type ProvidersDocument,
  type ProvidersPatch,
} from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DiffEditor from '@/components/DiffEditor.vue'
import Adapters from '@/components/Adapters.vue'
import ProtocolEnd from '@/components/ProtocolEnd.vue'
import McpServers from '@/components/McpServers.vue'
import ProbeBadge from '@/components/ProbeBadge.vue'
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

/* ------------------------------------------------------------------ provider presets */
/*
 * The empty row asks for four values nobody can invent: base_url, model, and a key that
 * lives on some other website. A preset fills the three that are public knowledge and
 * leaves exactly one field for the operator: the key. This is the difference between "read
 * the docs" and "paste one thing".
 */
interface Preset {
  key: string
  label: string
  kind: string
  base_url: string
  model: string
}

/* Brand names stay as-is; anything that is a sentence lives in i18n (config.presetKey.*). */
const PRESETS: Preset[] = [
  { key: 'deepseek', label: 'DeepSeek', kind: 'openai_compat', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-flash' },
  { key: 'qwen', label: 'Qwen', kind: 'openai_compat', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { key: 'openai', label: 'OpenAI', kind: 'openai_compat', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { key: 'ollama', label: 'Ollama', kind: 'openai_compat', base_url: 'http://127.0.0.1:11434/v1', model: 'llama3.1' },
]

const lastPreset = ref<Preset | null>(null)

function addPreset(preset: Preset): void {
  const id = `provider-${drafts.value.length + 1}`
  drafts.value.push({
    id,
    kind: preset.kind,
    base_url: preset.base_url,
    api_key: '',
    model: preset.model,
    priority: (drafts.value.length + 1) * 10,
    enabled: true,
  })
  markEdited(id)
  lastPreset.value = preset
}

function addRow(): void {
  const id = `provider-${drafts.value.length + 1}`
  drafts.value.push({
    id,
    kind: 'openai_compat',
    base_url: '',
    // Empty, not the "unchanged" sentinel: a sentinel in a brand-new row reads as a
    // placeholder the operator is supposed to keep, and saving it writes a literal marker.
    api_key: '',
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

/* --------------------------------------------------------------- probe (no writes) */

/**
 * One result per row, keyed by position. Position, not id: the id field is editable, and
 * keying by a value the operator can retype mid-test would detach the answer from the row
 * that asked for it.
 */
const probes = ref<Record<string, ProbeResult | null>>({})
const probing = ref<Record<string, boolean>>({})
const probeErrors = ref<Record<string, string>>({})

async function testProvider(row: ProviderEntry, index: number): Promise<void> {
  const key = String(index)
  probing.value = { ...probing.value, [key]: true }
  probeErrors.value = { ...probeErrors.value, [key]: '' }
  probes.value = { ...probes.value, [key]: null }
  try {
    // The draft value, not the saved one. "Test before you save" is the whole feature;
    // using the file's base_url would make the button useless during the edit that needs
    // it. Nothing here touches `edited`, so a probe never dirties the form.
    probes.value = {
      ...probes.value,
      [key]: await api.configProvidersTest({ id: row.id, base_url: row.base_url ?? '' }),
    }
  } catch (err) {
    probeErrors.value = { ...probeErrors.value, [key]: (err as Error).message }
  } finally {
    probing.value = { ...probing.value, [key]: false }
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
        <!-- Says what the test button does *not* do. "Test connection" would otherwise be
             read as "test my key", and a 401 would look like a broken panel. -->
        <p class="hint" style="margin: 0 0 8px">{{ t('probe.providerHint') }}</p>
        <!-- Every column explained once, in the place where it is filled in. The three
             values people get wrong most often are named explicitly. -->
        <ul class="hint fieldmap">
          <li>{{ t('config.hint.id') }}</li>
          <li>{{ t('config.hint.baseUrl') }}</li>
          <li>{{ t('config.hint.model') }}</li>
          <li>{{ t('config.hint.key') }}</li>
        </ul>

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
              <th scope="col">{{ t('probe.column') }}</th>
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
                  placeholder="openai_compat"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <input
                  v-model="row.base_url"
                  class="field"
                  style="min-width: 180px"
                  placeholder="https://api.deepseek.com/v1"
                  aria-label="Base URL"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <input
                  v-model="row.model"
                  class="field"
                  style="min-width: 120px"
                  placeholder="deepseek-flash"
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
                  placeholder="sk-... / env:DEEPSEEK_API_KEY"
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
                <!-- Enabled by the draft base_url, not by `edited`: a provider can be
                     tested the moment its address is typed, before anything is saved. -->
                <button
                  class="btn ghost"
                  type="button"
                  :disabled="probing[index] || !row.base_url"
                  :aria-label="t('probe.ariaTest', { id: row.id })"
                  @click="testProvider(row, index)"
                >
                  {{ probing[index] ? t('probe.testing') : t('probe.test') }}
                </button>
                <ProbeBadge :result="probes[index] ?? null" />
                <span v-if="probeErrors[index]" class="hint" style="margin-left: 8px">
                  {{ t('probe.failed', { reason: probeErrors[index] }) }}
                </span>
              </td>
              <td>
                <button class="btn ghost" type="button" @click="removeRow(index)">{{ t('config.remove') }}</button>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- One click fills kind/base_url/model; the key is the only thing left to paste.
             A blank row asks for three facts that live on other websites. -->
        <div class="row presets" style="margin-top: 10px">
          <span class="hint">{{ t('config.presetLabel') }}</span>
          <button
            v-for="preset in PRESETS"
            :key="preset.key"
            class="btn ghost"
            type="button"
            @click="addPreset(preset)"
          >
            + {{ preset.label }}
          </button>
        </div>
        <p v-if="lastPreset" class="hint" style="margin: 4px 0 0">
          {{
            t('config.presetHint', {
              site: t(`config.presetKey.${lastPreset.key}`),
              model: lastPreset.model,
            })
          }}
        </p>

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
  <!-- Before the adapter table: the table's hardest field is the address, and this card
       exists so the operator never has to know it. -->
  <ProtocolEnd />
  <Adapters />
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
              <!-- Focusable and Enter/Space-operable: the row is a disclosure, and a
                   mouse-only one is a dead end for anyone who tabs through the table. -->
              <tr
                style="cursor: pointer"
                tabindex="0"
                :aria-expanded="expanded === row.id"
                @click="toggle(row.id)"
                @keydown.enter.prevent="toggle(row.id)"
                @keydown.space.prevent="toggle(row.id)"
              >
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
