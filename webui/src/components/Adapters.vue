<script setup lang="ts">
/**
 * Adapter (protocol end) editor: read -> diff -> apply.
 *
 * The field names are the ones `config/adapters.yaml` actually documents, not
 * guesses: `account_id`, `mode`, `ws_url` (forward) or `host`+`port` (reverse), and
 * `access_token`. An earlier version of this form used `token` and `self_id`, which the
 * adapter silently ignores — the options bag is free-form, so a wrong name produces a
 * saved file that looks right and a connection that never opens.
 */
import { onMounted, ref } from 'vue'

import { api, type AdapterProbeResult } from '@/api/client'
import ProbeBadge from '@/components/ProbeBadge.vue'
import { t } from '@/i18n'

interface Draft {
  kind: string
  mode: string
  account_id: string
  ws_url: string
  host: string
  port: string
  access_token: string
  enabled: boolean
}

const drafts = ref<Draft[]>([])
const baseHash = ref('')
const diff = ref('')
const newHash = ref('')
const status = ref('')
const busy = ref(false)
const loaded = ref(false)

function blank(): Draft {
  return {
    kind: 'onebot11',
    mode: 'forward',
    account_id: '',
    ws_url: 'ws://127.0.0.1:3001',
    host: '',
    port: '',
    access_token: '',
    enabled: true,
  }
}

function message(text: string) {
  status.value = text
}

function failure(key: string, error: unknown) {
  message(t(key, { reason: (error as Error).message }))
}

async function load() {
  busy.value = true
  try {
    const body = await api.configAdapters()
    baseHash.value = body.base_hash
    const entries = body.document?.adapters ?? []
    drafts.value = entries.map((entry: Record<string, unknown>) => ({
      kind: String(entry.kind ?? ''),
      mode: String(entry.mode ?? 'forward'),
      account_id: String(entry.account_id ?? ''),
      ws_url: String(entry.ws_url ?? ''),
      host: String(entry.host ?? ''),
      port: String(entry.port ?? ''),
      // Masked by the server unless it is an `env:` reference; the sentinel keeps an
      // untouched value from being written back as the mask itself.
      access_token: String(entry.access_token ?? ''),
      enabled: entry.enabled !== false,
    }))
    loaded.value = true
    diff.value = ''
    message('')
  } catch (error) {
    failure('adapters.loadFailed', error)
  } finally {
    busy.value = false
  }
}

function payload() {
  return drafts.value.map((draft) => {
    const entry: Record<string, unknown> = {
      kind: draft.kind.trim(),
      enabled: draft.enabled,
      account_id: draft.account_id.trim(),
      mode: draft.mode,
      access_token: draft.access_token.trim(),
    }
    // Only the keys the chosen mode uses: sending a stale `host` with mode=forward is
    // how a file ends up with two connection targets and no way to tell which wins.
    if (draft.mode === 'reverse') {
      entry.host = draft.host.trim()
      entry.port = draft.port.trim()
    } else {
      entry.ws_url = draft.ws_url.trim()
    }
    return entry
  })
}

async function preview() {
  busy.value = true
  try {
    const body = await api.configAdaptersDiff({
      adapters: payload(),
      base_hash: baseHash.value,
    })
    diff.value = body.diff || ''
    newHash.value = body.new_hash
    message(body.empty ? t('adapters.noChanges') : t('adapters.review'))
  } catch (error) {
    failure('adapters.previewFailed', error)
  } finally {
    busy.value = false
  }
}

async function write() {
  busy.value = true
  try {
    const body = await api.configAdaptersApply({
      adapters: payload(),
      base_hash: baseHash.value,
      approved_hash: newHash.value,
    })
    message(
      body.written
        ? t('adapters.written')
        : t('adapters.notWritten', { reason: body.reason ?? t('adapters.noChanges') }),
    )
    await load()
  } catch (error) {
    failure('adapters.writeFailed', error)
  } finally {
    busy.value = false
  }
}

/* ------------------------------------------------------------------ probe */
/*
 * `forward` and `reverse` answer different questions, and the UI must not blur them:
 * forward does a real handshake plus one `get_login_info` (a handshake alone does not
 * prove the far side is OneBot), while reverse can only report on the port it would bind
 * — nothing here can see a peer that has not dialled in yet.
 *
 * The token is sent as-is even when it is the server's mask: the server substitutes the
 * saved value, so testing a stored row works without retyping a secret that the panel is
 * deliberately not showing.
 */
const probes = ref<Record<number, AdapterProbeResult | null>>({})
const probing = ref<Record<number, boolean>>({})
const probeErrors = ref<Record<number, string>>({})

async function testAdapter(draft: Draft, index: number): Promise<void> {
  probing.value = { ...probing.value, [index]: true }
  probeErrors.value = { ...probeErrors.value, [index]: '' }
  probes.value = { ...probes.value, [index]: null }
  try {
    probes.value = {
      ...probes.value,
      [index]: await api.configAdaptersTest({
        kind: draft.kind.trim() || 'onebot11',
        mode: draft.mode,
        ws_url: draft.mode === 'forward' ? draft.ws_url.trim() : '',
        host: draft.mode === 'reverse' ? draft.host.trim() : '',
        port: draft.mode === 'reverse' ? Number(draft.port) || null : null,
        access_token: draft.access_token.trim(),
      }),
    }
  } catch (error) {
    probeErrors.value = { ...probeErrors.value, [index]: (error as Error).message }
  } finally {
    probing.value = { ...probing.value, [index]: false }
  }
}

/* ------------------------------------------------- what the other side must dial */
/*
 * Both modes need an answer typed into *another program's* UI, and that answer is
 * derived, not remembered: forward uses the ws url as-is, reverse needs `host:port`
 * composed into a url. `0.0.0.0` is the usual bind address but is meaningless to a peer,
 * so it is rewritten to the host the operator is actually looking at — otherwise someone
 * pastes `ws://0.0.0.0:3001` into NapCat and gets a connection refused.
 */
const copied = ref<Record<number, boolean>>({})
const copyError = ref('')

const panelHost = window.location.hostname || '127.0.0.1'

function peerTarget(draft: Draft): string {
  if (draft.mode !== 'reverse') {
    return draft.ws_url.trim() || 'ws://…'
  }
  const host = draft.host.trim() || '127.0.0.1'
  const visibleHost = host === '0.0.0.0' || host === '::' ? panelHost : host
  if (!draft.port.trim()) return `ws://${visibleHost}:…`
  return `ws://${visibleHost}:${draft.port.trim()}`
}

async function copyTarget(draft: Draft, index: number): Promise<void> {
  const text = peerTarget(draft)
  copyError.value = ''
  try {
    await navigator.clipboard.writeText(text)
    copied.value = { ...copied.value, [index]: true }
    window.setTimeout(() => {
      copied.value = { ...copied.value, [index]: false }
    }, 2000)
  } catch {
    // Clipboard access needs a secure context; over plain HTTP on a LAN address it is
    // refused, and silently failing would look like nothing happened.
    copyError.value = t('adapters.copyFailed', { text })
  }
}

/** The paste-into-NapCat line only means something for OneBot. A QQ-official adapter is
 * configured with an app id and secret, and showing it a `ws://` address to paste is worse
 * than showing nothing: it sends someone looking for a field inside NapCat that does not
 * exist. */
function isOneBot(draft: Draft): boolean {
  return (draft.kind || 'onebot11').toLowerCase().startsWith('onebot')
}

function onModeChange(draft: Draft): void {
  if (draft.mode === 'reverse' && !draft.host && !draft.port) {
    draft.host = '127.0.0.1'
    draft.port = '3001'
  }
}

onMounted(load)
</script>

<template>
  <section class="panel">
    <h2>{{ t('adapters.title') }}</h2>
    <p class="muted">{{ t('adapters.hint') }}</p>

    <!-- Expanded by default: this is the block a first-time operator reads, and a
         collapsed "help" toggle is exactly how "怎么配置" stays unanswered. The recipes
         name the *other* program's UI (NapCat) because the hardest part of this form is
         not the fields — it is knowing which side of the connection each field describes. -->
    <details class="howto" open>
      <summary>{{ t('adapters.howtoSummary') }}</summary>
      <p class="muted">{{ t('adapters.howtoPrelude') }}</p>

      <h3>{{ t('adapters.howtoReverseTitle') }}</h3>
      <ol>
        <li>{{ t('adapters.howtoReverse1') }}</li>
        <li>{{ t('adapters.howtoReverse2') }}</li>
        <li>{{ t('adapters.howtoReverse3') }}</li>
        <li>{{ t('adapters.howtoReverse4') }}</li>
      </ol>

      <h3>{{ t('adapters.howtoForwardTitle') }}</h3>
      <ol>
        <li>{{ t('adapters.howtoForward1') }}</li>
        <li>{{ t('adapters.howtoForward2') }}</li>
        <li>{{ t('adapters.howtoForward3') }}</li>
      </ol>

      <h3>{{ t('adapters.howtoCommonTitle') }}</h3>
      <ul>
        <li>{{ t('adapters.howtoCommon1') }}</li>
        <li>{{ t('adapters.howtoCommon2') }}</li>
        <li>{{ t('adapters.howtoCommon3') }}</li>
      </ul>
    </details>

    <p v-if="!loaded" class="muted">
      {{ busy ? t('adapters.loading') : t('adapters.notLoaded') }}
    </p>

    <!-- Rendered whenever the document loaded, never gated on there being rows: a
         hidden table plus an enabled "add" button is how a click lands nowhere. -->
    <table>
      <thead>
        <tr>
          <th>{{ t('adapters.col.kind') }}</th>
          <th>{{ t('adapters.col.mode') }}</th>
          <th>{{ t('adapters.col.account') }}</th>
          <th>{{ t('adapters.col.ws') }}</th>
          <th>{{ t('adapters.col.host') }}</th>
          <th>{{ t('adapters.col.port') }}</th>
          <th>{{ t('adapters.col.token') }}</th>
          <th>{{ t('adapters.col.enabled') }}</th>
          <th>{{ t('probe.column') }}</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(draft, index) in drafts" :key="index">
          <tr>
            <td>
              <input v-model="draft.kind" class="adapter-field" placeholder="onebot11" />
              <span class="field-hint">{{ t('adapters.hint.kind') }}</span>
            </td>
            <td>
              <!-- Switching fills the reverse values in, so the row is never half-empty in
                   a way the operator has to diagnose. -->
              <select v-model="draft.mode" class="adapter-field" @change="onModeChange(draft)">
                <option value="forward">forward</option>
                <option value="reverse">reverse</option>
              </select>
              <span class="field-hint">{{ t('adapters.hint.mode') }}</span>
            </td>
            <td>
              <input
                v-model="draft.account_id"
                class="adapter-field"
                :placeholder="t('adapters.ph.account')"
              />
              <span class="field-hint">{{ t('adapters.hint.account') }}</span>
            </td>
            <td>
              <input
                v-model="draft.ws_url"
                class="adapter-field"
                :disabled="draft.mode === 'reverse'"
                placeholder="ws://127.0.0.1:3001"
              />
              <span class="field-hint">{{ t('adapters.hint.ws') }}</span>
            </td>
            <td>
              <input
                v-model="draft.host"
                class="adapter-field"
                :disabled="draft.mode !== 'reverse'"
                placeholder="127.0.0.1"
              />
              <span class="field-hint">{{ t('adapters.hint.host') }}</span>
            </td>
            <td>
              <input
                v-model="draft.port"
                class="adapter-field"
                :disabled="draft.mode !== 'reverse'"
                placeholder="3001"
              />
              <span class="field-hint">{{ t('adapters.hint.port') }}</span>
            </td>
            <td>
              <input v-model="draft.access_token" class="adapter-field" />
              <span class="field-hint">{{ t('adapters.hint.token') }}</span>
            </td>
            <td><input v-model="draft.enabled" type="checkbox" class="adapter-check" /></td>
            <td>
              <button
                class="btn ghost"
                type="button"
                :disabled="probing[index]"
                :aria-label="t('probe.ariaTestKind', { kind: draft.kind || 'onebot11' })"
                @click="testAdapter(draft, index)"
              >
                {{ probing[index] ? t('probe.testing') : t('probe.test') }}
              </button>
              <ProbeBadge :result="probes[index] ?? null" />
              <div v-if="probeErrors[index]" class="muted">
                {{ t('probe.failed', { reason: probeErrors[index] }) }}
              </div>
            </td>
          </tr>

          <!-- The line that ends the guessing: exactly what to paste into the *other*
               program. AstrBot's answer to "representative config" is a template with
               working defaults; the part it still leaves to the operator is which host
               NapCat should dial, so that is computed here instead. -->
          <tr v-if="isOneBot(draft)" class="target-row">
            <td colspan="9">
              <span class="muted">
                {{ draft.mode === 'reverse'
                  ? t('adapters.targetLabelReverse')
                  : t('adapters.targetLabelForward') }}
              </span>
              <code class="target">{{ peerTarget(draft) }}</code>
              <button class="btn ghost" type="button" @click="copyTarget(draft, index)">
                {{ copied[index] ? t('adapters.copied') : t('adapters.copy') }}
              </button>
              <span v-if="copyError" class="muted">{{ copyError }}</span>
              <span class="muted">
                {{ draft.mode === 'reverse'
                  ? t('adapters.targetHintReverse')
                  : t('adapters.targetHintForward') }}
              </span>
            </td>
          </tr>
        </template>
        <tr v-if="loaded && !drafts.length">
          <td colspan="9" class="muted">{{ t('adapters.empty') }}</td>
        </tr>
      </tbody>
    </table>

    <!-- The one sentence that stops someone waiting for a connection this check cannot
         observe: in reverse mode the peer dials us, so only the port is knowable. -->
    <p class="muted">{{ t('probe.adapterHint') }}</p>

    <div class="row">
      <button class="btn" :disabled="busy || !loaded" @click="drafts.push(blank())">
        {{ t('adapters.add') }}
      </button>
      <button class="btn lamp" :disabled="busy || !loaded" @click="preview">
        {{ t('adapters.preview') }}
      </button>
      <button class="btn" :disabled="busy || !diff" @click="write">
        {{ t('adapters.write') }}
      </button>
    </div>

    <p v-if="status" class="muted">{{ status }}</p>
    <pre v-if="diff" class="diff">{{ diff }}</pre>
  </section>
</template>

<style scoped>
/* Inputs inside a table cell inherit the browser's default width, which made every row
   ragged: one column stretched while the checkbox cell collapsed. Scoped here rather
   than in base.css because this is the only table whose cells are all editable. */
.adapter-field {
  width: 100%;
  min-width: 6rem;
  box-sizing: border-box;
}
.adapter-check {
  margin: 0;
}
td {
  vertical-align: middle;
}
.howto {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2);
  padding: 10px 14px;
  margin: 0 0 14px;
}
.howto summary {
  cursor: pointer;
  font-weight: 600;
}
.howto h3 {
  margin: 10px 0 4px;
  font-size: 0.95rem;
}
.howto ol,
.howto ul {
  margin: 4px 0 4px 20px;
  padding: 0;
}
.howto li {
  margin: 3px 0;
}
.field-hint {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  line-height: 1.35;
  color: var(--ink-3);
}
.target-row td {
  border-top: none;
  padding-top: 0;
  background: var(--surface-2);
}
.target {
  font-family: var(--mono);
  user-select: all;
  margin: 0 6px;
}
</style>
