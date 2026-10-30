<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  api,
  type McpApplyResult,
  type McpPatch,
  type McpServerDocument,
  type McpServerPatchEntry,
} from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DiffEditor from '@/components/DiffEditor.vue'
import { t } from '@/i18n'

/**
 * Editing `config/mcp.yaml` from the panel: read → diff → confirm → write.
 *
 * Three decisions are visible in the markup and worth stating once:
 *
 * 1. **The command is one argument per line, not a space-separated string.** Splitting
 *    on spaces is where quoting turns "read a file" into "run a shell" — the same reason
 *    the backend refuses to store a string. A textarea cannot express the ambiguity.
 * 2. **Env values are write-only.** The server returns key names, so an untouched field
 *    is omitted from the patch and the file keeps its value. There is no mask to echo
 *    back, which is what makes the provider-style "saved *** over the token" bug
 *    unreachable here.
 * 3. **The name is not editable after load.** It is the key the patch merges on, so
 *    editing it would append a second server rather than rename this one.
 */
interface Draft {
  /** Stable list key: the on-disk name, or a generated id for a row not yet saved. */
  key: string
  name: string
  description: string
  /** One argv element per line. */
  commandText: string
  timeout: number
  min_role: string
  envText: string
  envKeys: string[]
  isNew: boolean
  pendingDelete: boolean
}

interface DiffView {
  diff: string
  changed_fields: string[]
  new_hash: string
  empty: boolean
}

const doc = ref<McpServerDocument | null>(null)
const drafts = ref<Draft[]>([])
const edited = ref<Record<string, boolean>>({})
const expanded = ref('')
const busy = ref(false)
const error = ref('')
const diff = ref<DiffView | null>(null)
const confirmOpen = ref(false)
const outcome = ref<McpApplyResult | null>(null)

const roles = computed(() => doc.value?.roles ?? [])
const liveStatus = computed(() => outcome.value?.servers ?? doc.value?.status ?? {})
const pendingCount = computed(
  () => drafts.value.filter((row) => edited.value[row.key] || row.pendingDelete).length,
)

function statusOf(name: string): { tools: number; error: string } | undefined {
  return liveStatus.value[name]
}

function statusTone(name: string): string {
  const state = statusOf(name)
  if (!state) return 'warn'
  if (state.error) return 'bad'
  return state.tools > 0 ? 'ok' : 'warn'
}

function statusText(name: string): string {
  const state = statusOf(name)
  if (!state) return t('config.mcpUnknown')
  if (state.error) return `${t('config.mcpFailed')} · ${state.error}`
  return state.tools > 0
    ? t('config.mcpConnected', { n: state.tools })
    : t('config.mcpNoTools')
}

async function load(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    const body = await api.configMcp()
    doc.value = body
    drafts.value = body.servers.map((row) => ({
      key: row.name,
      name: row.name,
      description: row.description,
      commandText: row.command.join('\n'),
      timeout: row.timeout,
      min_role: row.min_role,
      envText: '',
      envKeys: row.env_keys,
      isNew: false,
      pendingDelete: false,
    }))
    edited.value = {}
    diff.value = null
    outcome.value = null
  } catch (err) {
    // A parse failure arrives as 422 with the YAML error. Rendering an empty table
    // instead would invite the operator to "add" servers over a file with a typo in it.
    error.value = (err as Error).message
  } finally {
    busy.value = false
  }
}

function markEdited(key: string): void {
  edited.value = { ...edited.value, [key]: true }
  outcome.value = null
}

function addRow(): void {
  const key = `new-${Date.now()}`
  drafts.value.push({
    key,
    name: '',
    description: '',
    commandText: '',
    timeout: 20,
    min_role: 'member',
    envText: '',
    envKeys: [],
    isNew: true,
    pendingDelete: false,
  })
  markEdited(key)
  expanded.value = key
}

function toggle(key: string): void {
  expanded.value = expanded.value === key ? '' : key
}

function requestDelete(row: Draft): void {
  if (row.isNew && !edited.value[row.key]) {
    drafts.value = drafts.value.filter((item) => item.key !== row.key)
    return
  }
  row.pendingDelete = true
  expanded.value = ''
  outcome.value = null
}

function undoDelete(row: Draft): void {
  row.pendingDelete = false
  outcome.value = null
}

/** `""` means "keep what is on disk"; a non-empty textarea replaces the whole mapping. */
function parseEnv(text: string): Record<string, string> | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const env: Record<string, string> = {}
  for (const line of trimmed.split('\n')) {
    const item = line.trim()
    if (!item) continue
    const at = item.indexOf('=')
    if (at <= 0) continue
    env[item.slice(0, at).trim()] = item.slice(at + 1)
  }
  return env
}

function buildPatch(): McpPatch | null {
  const servers: McpServerPatchEntry[] = []
  for (const row of drafts.value) {
    if (!edited.value[row.key] && !row.pendingDelete) continue
    if (row.pendingDelete) {
      // A row that was never saved has nothing to delete on disk.
      if (!row.isNew) servers.push({ name: row.name, delete: true })
      continue
    }
    const name = row.name.trim()
    if (!name) {
      error.value = t('config.mcpName')
      return null
    }
    const command = row.commandText
      .split('\n')
      .map((part) => part.trim())
      .filter(Boolean)
    if (!command.length) {
      error.value = t('config.mcpCommandHint')
      return null
    }
    const entry: McpServerPatchEntry = {
      name,
      description: row.description,
      command,
      timeout: row.timeout,
      min_role: row.min_role,
    }
    const env = parseEnv(row.envText)
    if (env) entry.env = env
    servers.push(entry)
  }
  return { base_hash: doc.value?.base_hash ?? '', servers }
}

async function previewDiff(): Promise<void> {
  const payload = buildPatch()
  if (!payload) return
  if (!payload.servers.length) {
    error.value = t('config.noEditsYet')
    return
  }
  busy.value = true
  error.value = ''
  try {
    diff.value = await api.configMcpDiff(payload)
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    busy.value = false
  }
}

async function applyChanges(): Promise<void> {
  const payload = buildPatch()
  if (!payload || !diff.value) return
  busy.value = true
  error.value = ''
  try {
    const body = await api.configMcpApply({ ...payload, approved_hash: diff.value.new_hash })
    if (!body.written) {
      error.value = t('config.notWritten', { reason: body.reason ?? t('config.noChange') })
      return
    }
    confirmOpen.value = false
    diff.value = null
    await load()
    // `load()` clears the outcome; put the per-server result back so the table can show
    // which server actually came up. Written and working are different claims.
    outcome.value = body
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    busy.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('config.mcp') }}</h2>
      <span class="tag">{{ t('common.rows', { n: drafts.length }) }}</span>
      <span class="strip__spacer" />
      <span class="hint">{{ t('config.mcpHint') }}</span>
      <button class="btn ghost" type="button" :disabled="busy" @click="load">
        {{ t('common.refresh') }}
      </button>
    </div>

    <div class="panel__body">
      <p class="warn-banner" style="margin: 0 0 10px">{{ t('config.mcpOwnerOnly') }}</p>

      <p v-if="error" class="error-banner" role="alert">{{ error }}</p>

      <div v-if="!drafts.length" class="empty">{{ t('config.mcpNoServers') }}</div>

      <table v-else class="data">
        <caption class="visually-hidden">{{ t('config.mcp') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('config.mcpName') }}</th>
            <th scope="col">{{ t('config.mcpCommand') }}</th>
            <th scope="col">{{ t('config.mcpMinRole') }}</th>
            <th scope="col">{{ t('common.status') }}</th>
            <th scope="col"><span class="visually-hidden">{{ t('common.actions') }}</span></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in drafts" :key="row.key">
            <tr :class="{ 'row--gone': row.pendingDelete }">
              <!-- Not uppercased like the other row headers: this string is the key the
                   patch matches on, and showing `FS` for `fs` invites a save that adds a
                   second server instead of editing the first. -->
              <th scope="row" class="cell--name">{{ row.name || '—' }}</th>
              <td class="mono cell--command" :title="row.commandText">
                {{ row.commandText.split('\n').filter(Boolean).join(' ') || '—' }}
              </td>
              <td>{{ row.min_role }}</td>
              <td>
                <span v-if="row.pendingDelete" class="tag bad">{{ t('config.mcpDelete') }}</span>
                <span v-else class="tag" :class="statusTone(row.name)">{{ statusText(row.name) }}</span>
              </td>
              <td class="cell--actions">
                <template v-if="row.pendingDelete">
                  <button class="btn ghost" type="button" @click="undoDelete(row)">
                    {{ t('common.cancel') }}
                  </button>
                </template>
                <template v-else>
                  <button class="btn ghost" type="button" @click="toggle(row.key)">
                    {{ expanded === row.key ? t('config.mcpClose') : t('config.mcpEdit') }}
                  </button>
                  <button class="btn ghost" type="button" @click="requestDelete(row)">
                    {{ t('config.mcpDelete') }}
                  </button>
                </template>
              </td>
            </tr>

            <tr v-if="expanded === row.key && !row.pendingDelete">
              <td colspan="5">
                <div class="edit">
                  <div class="edit__grid">
                    <label class="field-line">
                      <span>{{ t('config.mcpName') }}</span>
                      <input
                        v-model="row.name"
                        class="field"
                        :disabled="!row.isNew"
                        :title="row.isNew ? '' : t('config.mcpNameLocked')"
                        @input="markEdited(row.key)"
                      />
                    </label>
                    <label class="field-line">
                      <span>{{ t('config.mcpMinRole') }}</span>
                      <select v-model="row.min_role" class="field" @change="markEdited(row.key)">
                        <option v-for="role in roles" :key="role" :value="role">{{ role }}</option>
                      </select>
                    </label>
                    <label class="field-line">
                      <span>{{ t('config.mcpTimeout') }}</span>
                      <input
                        v-model.number="row.timeout"
                        class="field"
                        type="number"
                        min="1"
                        @input="markEdited(row.key)"
                      />
                    </label>
                  </div>

                  <label class="field-line field-line--block">
                    <span>{{ t('config.mcpCommand') }}</span>
                    <textarea
                      v-model="row.commandText"
                      class="field mono"
                      rows="3"
                      spellcheck="false"
                      :placeholder="t('config.mcpCommandHint')"
                      @input="markEdited(row.key)"
                    />
                  </label>

                  <label class="field-line field-line--block">
                    <span>{{ t('config.mcpEnv') }}</span>
                    <textarea
                      v-model="row.envText"
                      class="field mono"
                      rows="2"
                      spellcheck="false"
                      :placeholder="
                        row.envKeys.length
                          ? t('config.mcpEnvHint', { n: row.envKeys.length })
                          : t('config.mcpEnvNew')
                      "
                      @input="markEdited(row.key)"
                    />
                  </label>
                  <p v-if="row.envKeys.length" class="hint" style="margin: 4px 0 0">
                    {{ row.envKeys.join(' · ') }}
                  </p>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <div class="row" style="margin-top: 10px">
        <button class="btn ghost" type="button" @click="addRow">{{ t('config.mcpAdd') }}</button>
        <span class="strip__spacer" />
        <span class="hint">{{ t('config.dirtyCount', { n: pendingCount }) }}</span>
        <button
          class="btn lamp"
          type="button"
          :disabled="busy || !pendingCount"
          @click="previewDiff"
        >
          {{ busy ? t('config.computing') : t('config.previewDiff') }}
        </button>
      </div>

      <p v-if="outcome" class="hint" style="margin-top: 8px" role="status">
        {{ outcome.restart_required ? t('config.mcpRestartNote') : t('config.mcpApplied') }}
        <span v-if="outcome.note"> · {{ outcome.note }}</span>
      </p>
    </div>
  </section>

  <section v-if="diff" class="panel">
    <div class="panel__head">
      <h2>{{ t('config.pendingChanges') }}</h2>
      <span class="tag">{{ t('config.fieldsCount', { n: diff.changed_fields.length }) }}</span>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" @click="diff = null">{{ t('common.cancel') }}</button>
      <button class="btn lamp" type="button" :disabled="busy || diff.empty" @click="confirmOpen = true">
        {{ t('config.confirmWrite') }}
      </button>
    </div>
    <div class="panel__body">
      <p class="warn-banner" style="margin: 0 0 10px">{{ t('config.mcpDiffHint') }}</p>
      <DiffEditor :diff="diff.diff" filename="mcp.yaml" />
    </div>
  </section>

  <ConfirmDialog
    :open="confirmOpen"
    :title="t('config.mcpConfirmTitle')"
    :detail="t('config.mcpConfirmDetail', { n: diff?.changed_fields.length ?? 0 })"
    :confirm-label="t('config.write')"
    :busy="busy"
    @confirm="applyChanges"
    @cancel="confirmOpen = false"
  />
</template>

<style scoped>
.cell--name {
  text-transform: none;
}

.cell--command {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell--actions {
  white-space: nowrap;
  text-align: right;
}

.row--gone {
  opacity: 0.55;
}

.edit {
  padding: 8px 0 4px;
}

.edit__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}

.field-line {
  display: grid;
  gap: 4px;
  font-size: 11px;
  color: var(--ink-2);
}

.field-line--block {
  margin-top: 10px;
}

.field-line textarea {
  resize: vertical;
  min-height: 48px;
}
</style>
