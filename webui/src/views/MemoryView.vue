<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
import { datetime, fromNow, num, truncate } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const sessions = useAsync(() => api.memorySessions(100))
const stats = useAsync(() => api.memoryStats())
const knowledge = useAsync(() => api.knowledge())

const selected = ref('')
const timeline = ref<any[]>([])
const timelineError = ref('')
const timelineLoading = ref(false)

async function openSession(key: string): Promise<void> {
  selected.value = key
  timelineLoading.value = true
  timelineError.value = ''
  try {
    const result = await api.memoryTimeline(key, 80)
    timeline.value = result.messages ?? []
  } catch (err) {
    timelineError.value = (err as Error).message
    timeline.value = []
  } finally {
    timelineLoading.value = false
  }
}

const rows = computed<any[]>(() => sessions.data.value?.sessions ?? [])

const layerRows = computed(() => {
  const layers = stats.data.value?.layers ?? {}
  return Object.entries(layers).map(([name, count]) => ({ name, count: Number(count) }))
})

const documents = computed<any[]>(() => knowledge.data.value?.documents ?? [])

function roleLabel(role: string): string {
  return role === 'assistant' ? t('memory.roleAssistant') : t('memory.roleUser')
}

// ---------------------------------------------------------------- knowledge write
//
// The panel used to say "上传接口尚未开放". It now exists, so the panel that
// advertises it has to be able to use it — a UI that describes a capability it
// cannot reach is indistinguishable from a missing feature.
//
// Notices are stored as a key plus parameters rather than as finished text. Held as
// text, they froze in whatever language was active when the action ran, so a panel
// left open across a switch showed two languages at once. Server errors stay raw text
// because they arrive already formatted and are not ours to translate.
type Msg = { key: string; params?: Record<string, string | number> } | { text: string }

function render(msg: Msg | null): string {
  if (!msg) return ''
  return 'key' in msg ? t(msg.key, msg.params) : msg.text
}

const draftTitle = ref('')
const draftContent = ref('')
const draftId = ref('')
const saving = ref(false)
const saveError = ref<Msg | null>(null)
const saveNotice = ref<Msg | null>(null)

const saveErrorText = computed(() => render(saveError.value))
const saveNoticeText = computed(() => render(saveNotice.value))

async function submitDocument(): Promise<void> {
  saveError.value = null
  saveNotice.value = null
  if (!draftTitle.value.trim() || !draftContent.value.trim()) {
    saveError.value = { key: 'memory.errRequired' }
    return
  }
  saving.value = true
  try {
    const result = await api.ingestKnowledge({
      title: draftTitle.value.trim(),
      content: draftContent.value,
      doc_id: draftId.value.trim() || undefined,
    })
    saveNotice.value = result.replaced
      ? { key: 'memory.replaced', params: { id: result.doc_id, n: result.chunks } }
      : { key: 'memory.created', params: { id: result.doc_id, n: result.chunks } }
    draftContent.value = ''
    draftId.value = result.doc_id
    await knowledge.reload()
  } catch (err) {
    saveError.value = { text: (err as Error).message }
  } finally {
    saving.value = false
  }
}

function editDocument(doc: any): void {
  draftId.value = doc.doc_id
  draftTitle.value = doc.title || ''
  draftContent.value = ''
  saveNotice.value = { key: 'memory.loadedForEdit' }
  saveError.value = null
}

async function removeDocument(doc: any): Promise<void> {
  if (!window.confirm(t('memory.deleteConfirm', { name: doc.title || doc.doc_id }))) return
  saveError.value = null
  saveNotice.value = null
  try {
    const result = await api.deleteKnowledge(doc.doc_id)
    saveNotice.value = { key: 'memory.deleted', params: { n: result.chunks_removed } }
    if (draftId.value === doc.doc_id) {
      draftId.value = ''
      draftTitle.value = ''
    }
    await knowledge.reload()
  } catch (err) {
    saveError.value = { text: (err as Error).message }
  }
}

function resetDraft(): void {
  draftId.value = ''
  draftTitle.value = ''
  draftContent.value = ''
  saveNotice.value = null
  saveError.value = null
}
</script>

<template>
  <div class="grid cols-3">
    <div class="readout">
      <span class="readout__label">{{ t('memory.entries') }}</span>
      <span class="readout__value">{{ num(stats.data.value?.total) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('memory.sessionCount') }}</span>
      <span class="readout__value">{{ num(rows.length) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('memory.docCount') }}</span>
      <span class="readout__value">{{ num(documents.length) }}</span>
    </div>
  </div>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('common.session') }}</h2>
        <span class="hint">{{ t('memory.clickForTimeline') }}</span>
      </div>
      <div class="panel__body flush">
        <div class="scroll">
          <table v-if="rows.length" class="data"><caption class="visually-hidden">{{ t('common.session') }}</caption>
            <thead>
              <tr>
                <th scope="col">{{ t('common.session') }}</th>
                <th scope="col" class="num">{{ t('memory.messages') }}</th>
                <th scope="col">{{ t('memory.recent') }}</th>
              </tr>
            </thead>
            <tbody>
              <!-- Focusable and Enter/Space-operable for the same reason as the persona
                   table: selecting a row is the only way into a session's history. -->
              <tr
                v-for="row in rows"
                :key="row.session_key"
                style="cursor: pointer"
                tabindex="0"
                :style="selected === row.session_key ? 'background: var(--brand-soft)' : ''"
                @click="openSession(row.session_key)"
                @keydown.enter.prevent="openSession(row.session_key)"
                @keydown.space.prevent="openSession(row.session_key)"
              >
                <td class="key">{{ row.session_key }}</td>
                <td class="num">{{ num(row.message_count) }}</td>
                <td>{{ row.last_at ? fromNow(row.last_at) : '—' }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">{{ t('memory.noSessions') }}</div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('memory.layers') }}</h2>
      </div>
      <div class="panel__body flush">
        <table v-if="layerRows.length" class="data"><caption class="visually-hidden">{{ t('memory.layers') }}</caption>
          <tbody>
            <tr v-for="layer in layerRows" :key="layer.name">
              <td class="key">{{ layer.name }}</td>
              <td class="num">{{ layer.count < 0 ? t('memory.unreadable') : num(layer.count) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">{{ t('memory.disabled') }}</div>
      </div>
    </section>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('memory.timeline') }}</h2>
      <span v-if="selected" class="tag lamp">{{ selected }}</span>
      <span class="strip__spacer" />
      <span v-if="timeline.length" class="hint">{{ t('common.rows', { n: timeline.length }) }}</span>
    </div>
    <div class="panel__body flush">
      <div v-if="timelineError" class="panel__body">
        <div class="error-banner">{{ timelineError }}</div>
      </div>
      <div v-else-if="timelineLoading" class="empty">{{ t('common.loading') }}</div>
      <div v-else-if="!selected" class="empty">{{ t('memory.pickSession') }}</div>
      <div v-else-if="!timeline.length" class="empty">{{ t('memory.emptySession') }}</div>
      <div v-else class="scroll">
        <table class="data"><caption class="visually-hidden">{{ t('memory.timeline') }}</caption>
          <thead>
            <tr>
              <th scope="col">{{ t('common.time') }}</th>
              <th scope="col">{{ t('common.role') }}</th>
              <th scope="col">{{ t('common.content') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in timeline" :key="index">
              <td style="white-space: nowrap">{{ datetime(row.created_at) }}</td>
              <td>
                <span class="tag" :class="row.role === 'assistant' ? 'lamp' : ''">
                  {{ roleLabel(row.role) }}
                </span>
              </td>
              <td style="max-width: 620px">
                {{ truncate(row.content, 200) || t('memory.emptyContent') }}
                <span v-if="row.image_desc" class="tag" style="margin-left: 6px">{{ t('memory.imageTag') }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('memory.knowledgeDocs') }}</h2>
      <span class="tag">{{ documents.length }}</span>
      <span class="strip__spacer" />
      <button class="btn ghost" @click="resetDraft">{{ t('memory.newDoc') }}</button>
    </div>
    <div class="panel__body flush">
      <table v-if="documents.length" class="data"><caption class="visually-hidden">{{ t('memory.knowledgeDocs') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('memory.title') }}</th>
            <th scope="col">ID</th>
            <th scope="col" class="num">{{ t('memory.chunks') }}</th>
            <th scope="col" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="doc in documents" :key="doc.doc_id">
            <td class="key">{{ doc.title || t('memory.untitled') }}</td>
            <td>{{ doc.doc_id }}</td>
            <td class="num">{{ doc.chunks }}</td>
            <td style="white-space: nowrap">
              <button class="btn ghost" @click="editDocument(doc)">{{ t('memory.replace') }}</button>
              <button class="btn ghost" @click="removeDocument(doc)">{{ t('common.delete') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">
        {{ t('memory.emptyKnowledge') }}
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ draftId ? t('memory.replaceDoc') : t('memory.newDocPanel') }}</h2>
      <span v-if="draftId" class="tag lamp">{{ draftId }}</span>
      <span class="strip__spacer" />
      <span class="hint">{{ t('memory.chunkHint') }}</span>
    </div>
    <div class="panel__body">
      <div class="stack">
        <div class="row">
          <input
            v-model="draftTitle"
            class="field"
            style="flex: 1 1 260px"
            :placeholder="t('memory.titlePlaceholder')"
            maxlength="200"
          />
          <input
            v-model="draftId"
            class="field"
            style="flex: 0 1 220px"
            :placeholder="t('memory.idPlaceholder')"
            maxlength="64"
          />
        </div>
        <textarea
          v-model="draftContent"
          class="field"
          rows="8"
          :placeholder="t('memory.contentPlaceholder')"
        />
        <div class="row">
          <button class="btn lamp" :disabled="saving" @click="submitDocument">
            {{
              saving
                ? t('memory.saving')
                : draftId
                  ? t('memory.overwrite')
                  : t('memory.write')
            }}
          </button>
          <span v-if="saveNoticeText" class="hint">{{ saveNoticeText }}</span>
        </div>
        <div v-if="saveErrorText" class="error-banner">{{ saveErrorText }}</div>
      </div>
    </div>
  </section>

  <div v-if="sessions.error.value" class="error-banner">{{ sessions.error.value }}</div>
</template>
