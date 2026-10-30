<script setup lang="ts">
/**
 * Adapter (protocol end) editor: read -> diff -> apply.
 *
 * Deliberately the same three steps as the provider editor above it on this page, and
 * for the same reason: the operator approves concrete lines. A single save button would
 * mean the first time they see the resulting file is after it is already live.
 */
import { onMounted, ref } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'

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

function failure(key: string, error: unknown) {
  message(t(key, { reason: (error as Error).message }))
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
    failure('adapters.loadFailed', error)
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

onMounted(load)
</script>

<template>
  <section class="panel">
    <h2>{{ t('adapters.title') }}</h2>
    <p class="muted">{{ t('adapters.hint') }}</p>

    <table v-if="loaded">
      <thead>
        <tr>
          <th>{{ t('adapters.col.kind') }}</th>
          <th>{{ t('adapters.col.enabled') }}</th>
          <th>{{ t('adapters.col.ws') }}</th>
          <th>{{ t('adapters.col.token') }}</th>
          <th>{{ t('adapters.col.self') }}</th>
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

    <p v-else class="muted">
      {{ busy ? t('adapters.loading') : t('adapters.notLoaded') }}
    </p>

    <div class="row">
      <button class="btn" :disabled="busy" @click="drafts.push(blank())">
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
