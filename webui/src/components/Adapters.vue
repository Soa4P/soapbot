<script setup lang="ts">
/**
 * Adapter (protocol end) editor: read -> diff -> apply.
 *
 * Deliberately the same three steps as the provider editor above it on this page, and
 * for the same reason: the operator approves concrete lines. A single save button would
 * mean the first time they see the resulting file is after it is already live.
 *
 * Labels are English rather than t(...) on purpose for now: the i18n test requires every
 * key to exist in both dictionaries, and adding half a page's worth of keys in the same
 * change as the page itself is how one of them ends up missing.
 */
import { onMounted, ref } from 'vue'

import { api } from '@/api/client'

interface Draft {
  kind: string
  enabled: boolean
  ws_url: string
  token: string
  self_id: string
}

const drafts = ref<Draft[]>([])
const baseHash = ref('')
const sentinel = ref('__UNCHANGED__')
const diff = ref('')
const newHash = ref('')
const status = ref('')
const busy = ref(false)
const loaded = ref(false)

function blank(): Draft {
  return { kind: '', enabled: true, ws_url: '', token: '', self_id: '' }
}

function message(text: string) {
  status.value = text
}

async function load() {
  busy.value = true
  try {
    const body = await api.configAdapters()
    baseHash.value = body.base_hash
    sentinel.value = body.unchanged_sentinel ?? '__UNCHANGED__'
    const entries = body.document?.adapters ?? []
    drafts.value = entries.map((entry: Record<string, unknown>) => ({
      kind: String(entry.kind ?? ''),
      enabled: entry.enabled !== false,
      ws_url: String(entry.ws_url ?? ''),
      // The server masks literals and leaves `env:` references readable; sending the
      // mask back unchanged is what the sentinel is for.
      token: String(entry.token ?? ''),
      self_id: String(entry.self_id ?? ''),
    }))
    loaded.value = true
    diff.value = ''
    message('')
  } catch (error) {
    message(`load failed: ${(error as Error).message}`)
  } finally {
    busy.value = false
  }
}

function payload() {
  return drafts.value.map((draft) => ({
    kind: draft.kind.trim(),
    enabled: draft.enabled,
    ws_url: draft.ws_url.trim(),
    token: draft.token.trim(),
    self_id: draft.self_id.trim(),
  }))
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
    message(body.empty ? 'no changes' : 'review the diff, then write')
  } catch (error) {
    message(`preview failed: ${(error as Error).message}`)
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
        ? 'written - restart the container to connect the new adapter'
        : `not written: ${body.reason ?? 'no changes'}`,
    )
    await load()
  } catch (error) {
    message(`write failed: ${(error as Error).message}`)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="panel">
    <h2>Protocol ends (adapters)</h2>
    <p class="muted">
      One entry per adapter <strong>kind</strong>. The runtime registers one adapter per
      kind, so a second entry with the same kind would replace the first one's
      connection settings instead of adding an account.
    </p>

    <table v-if="loaded">
      <thead>
        <tr>
          <th>Kind</th>
          <th>Enabled</th>
          <th>WebSocket URL</th>
          <th>Token</th>
          <th>Self ID</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(draft, index) in drafts" :key="index">
          <td><input v-model="draft.kind" placeholder="onebot" /></td>
          <td><input v-model="draft.enabled" type="checkbox" /></td>
          <td><input v-model="draft.ws_url" placeholder="ws://127.0.0.1:3000" /></td>
          <td><input v-model="draft.token" /></td>
          <td><input v-model="draft.self_id" /></td>
        </tr>
      </tbody>
    </table>

    <p v-else class="muted">{{ busy ? 'loading...' : 'not loaded' }}</p>

    <div class="row">
      <button class="btn" :disabled="busy" @click="drafts.push(blank())">Add adapter</button>
      <button class="btn lamp" :disabled="busy || !loaded" @click="preview">
        Preview changes
      </button>
      <button class="btn" :disabled="busy || !diff" @click="write">Write</button>
    </div>

    <p v-if="status" class="muted">{{ status }}</p>
    <pre v-if="diff" class="diff">{{ diff }}</pre>
  </section>
</template>
