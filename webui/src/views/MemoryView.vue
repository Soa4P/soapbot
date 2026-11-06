<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import EmptyState from '@/components/EmptyState.vue'
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

// ------------------------------------------------------------------ scene layer
//
// The scene layer had no interface at all: the card was injected into every prompt and
// the portrait was computed and stored, but the only way to see either was to read the
// database. This section is the missing half — the same gap the knowledge page had.
//
// Two deliberate choices about what to show:
//
// * the **rendered prompt** is displayed verbatim, not just the fields. The fields are
//   the input; the prompt is what the model actually receives, and it is the thing an
//   operator needs to see to judge whether the card is any good.
// * **candidates are listed before anything is written**. The argument for keyword
//   clustering over embeddings is that a human can check it; a one-click "generate"
//   button would throw that away.

const scenes = useAsync(() => api.memoryScenes(100))

const sceneScope = ref('')
const sceneCard = ref<any>(null)
const scenePortrait = ref<any>(null)
const sceneLoading = ref(false)
const sceneError = ref('')
const sceneNotice = ref('')
const rebuilding = ref(false)

const skills = ref<any[]>([])
const candidates = ref<any[]>([])
const skillsLoading = ref(false)
const skillError = ref('')
const skillNotice = ref('')
const generating = ref('')

const sceneRows = computed<any[]>(() => scenes.data.value?.scenes ?? [])

/**
 * Monotonic token for scene loads.
 *
 * Clicking through a long list fires overlapping requests, and the network does not
 * answer in order. Without this, the slower response for scene A lands after the faster
 * response for scene B and overwrites it — the panel then shows B's header with A's
 * card, which looks like the backend returning the wrong data.
 */
let sceneRequest = 0

async function openScene(scope: string): Promise<void> {
  const token = ++sceneRequest
  sceneScope.value = scope
  sceneLoading.value = true
  sceneError.value = ''
  sceneNotice.value = ''
  skillError.value = ''
  skillNotice.value = ''

  // ``allSettled``, not ``all``: the three endpoints fail independently. With ``all``, a
  // 503 from the skill forge — which is a *state*, not an error — blanked the card and
  // portrait too, so a working scene rendered as a failure banner. Each failure is now
  // reported where it belongs and the other two still render.
  const [detail, skillList, candidateList] = await Promise.allSettled([
    api.memoryScene(scope),
    api.memorySkills(scope),
    api.memorySkillCandidates(scope),
  ])

  // A newer click already won; discarding this response is the whole point of the token.
  if (token !== sceneRequest) return

  if (detail.status === 'fulfilled') {
    sceneCard.value = detail.value.card
    scenePortrait.value = detail.value.portrait
  } else {
    sceneError.value = (detail.reason as Error).message
    sceneCard.value = null
    scenePortrait.value = null
  }

  if (skillList.status === 'fulfilled') {
    skills.value = skillList.value.skills ?? []
  } else {
    skillError.value = (skillList.reason as Error).message
    skills.value = []
  }

  if (candidateList.status === 'fulfilled') {
    candidates.value = candidateList.value.candidates ?? []
  } else if (!skillError.value) {
    skillError.value = (candidateList.reason as Error).message
    candidates.value = []
  }

  sceneLoading.value = false
}

async function rebuildScene(): Promise<void> {
  if (!sceneScope.value) return
  const scope = sceneScope.value
  rebuilding.value = true
  sceneError.value = ''
  sceneNotice.value = ''
  try {
    const result = await api.memorySceneRefresh(scope)
    if (scope !== sceneScope.value) return
    sceneCard.value = result.card
    scenePortrait.value = result.portrait
    sceneNotice.value = result.portrait_withheld
      ? t('memory.portraitWithheld')
      : t('memory.rebuilt')

    // The list carries `has_card` and the portrait confidence, so it has to be re-read:
    // leaving it alone would show "not built" next to a card the operator just built.
    await scenes.reload()

    // If the scope lost its last memory between opening and rebuilding, it is no longer in
    // the list — and the detail pane would keep showing a card for a scene that no longer
    // exists. Clearing it is the honest outcome; a stale card here is exactly the failure
    // ``refresh`` deletes portraits to avoid, reproduced in the UI.
    if (!sceneRows.value.some((row: any) => row.scope === scope)) {
      sceneScope.value = ''
      sceneCard.value = null
      scenePortrait.value = null
      skills.value = []
      candidates.value = []
      sceneNotice.value = ''
      return
    }

    const candidateList = await api.memorySkillCandidates(scope)
    if (scope === sceneScope.value) candidates.value = candidateList.candidates ?? []
  } catch (err) {
    if (scope === sceneScope.value) sceneError.value = (err as Error).message
  } finally {
    rebuilding.value = false
  }
}

async function createSkill(topic: string): Promise<void> {
  if (!sceneScope.value) return
  generating.value = topic
  skillError.value = ''
  skillNotice.value = ''
  try {
    const result = await api.generateSkill({ scope: sceneScope.value, topic })
    skillNotice.value = t('memory.skillCreated', { name: result.title })
    const [skillList, candidateList] = await Promise.all([
      api.memorySkills(sceneScope.value),
      api.memorySkillCandidates(sceneScope.value),
    ])
    skills.value = skillList.skills ?? []
    candidates.value = candidateList.candidates ?? []
  } catch (err) {
    skillError.value = (err as Error).message
  } finally {
    generating.value = ''
  }
}

async function removeSkill(skill: any): Promise<void> {
  if (!sceneScope.value) return
  if (!window.confirm(t('memory.skillDeleteConfirm', { name: skill.title }))) return
  skillError.value = ''
  skillNotice.value = ''
  try {
    await api.deleteSkill(sceneScope.value, skill.skill_id)
    skillNotice.value = t('memory.skillDeleted', { name: skill.title })
    const [skillList, candidateList] = await Promise.all([
      api.memorySkills(sceneScope.value),
      api.memorySkillCandidates(sceneScope.value),
    ])
    skills.value = skillList.skills ?? []
    candidates.value = candidateList.candidates ?? []
  } catch (err) {
    skillError.value = (err as Error).message
  }
}

function confidencePct(value: number): string {
  return `${Math.round((Number(value) || 0) * 100)}%`
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
          <EmptyState
            v-else
            :lead="t('memory.noSessions')"
            :hint="t('memory.noSessionsHint')"
            to="/settings"
            :action="t('memory.noSessionsAction')"
          />
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
      <EmptyState v-else-if="!selected" :lead="t('memory.pickSession')" :hint="t('memory.pickSessionHint')" />
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

  <!--
    Scene layer. Sits after the knowledge base because it is derived from memories, not
    authored: the page reads top-down as "what happened → what was written → what the bot
    concluded from it".
  -->
  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('memory.sceneLayer') }}</h2>
      <span class="strip__spacer" />
      <span class="hint">{{ t('memory.sceneHint') }}</span>
    </div>
    <div class="panel__body">
      <div v-if="scenes.error.value" class="error-banner">{{ scenes.error.value }}</div>

      <EmptyState
        v-else-if="!scenes.loading.value && sceneRows.length === 0"
        :lead="t('memory.sceneEmpty')"
      />

      <div v-else class="scene-grid">
        <ul class="scene-list">
          <li v-for="row in sceneRows" :key="row.scope">
            <button
              class="scene-item"
              :class="{ 'scene-item--on': row.scope === sceneScope }"
              @click="openScene(row.scope)"
            >
              <span class="scene-item__name">{{ row.title || row.scope }}</span>
              <span class="scene-item__meta">
                {{ t('memory.memoryCount', { n: row.memory_count }) }}
                <span v-if="row.has_card" class="tag lamp">{{ t('memory.card') }}</span>
                <span v-if="row.has_portrait" class="tag">
                  {{ t('memory.portrait') }} {{ confidencePct(row.portrait_confidence) }}
                </span>
              </span>
            </button>
          </li>
        </ul>

        <div class="scene-detail">
          <div v-if="!sceneScope" class="empty">{{ t('memory.scenePick') }}</div>
          <div v-else-if="sceneLoading" class="empty">{{ t('common.loading') }}</div>
          <div v-else-if="sceneError" class="error-banner">{{ sceneError }}</div>
          <div v-else class="stack">
            <div class="row">
              <strong class="mono">{{ sceneScope }}</strong>
              <span class="strip__spacer" />
              <button class="btn ghost" :disabled="rebuilding" @click="rebuildScene">
                {{ rebuilding ? t('memory.rebuilding') : t('memory.rebuild') }}
              </button>
            </div>
            <div v-if="sceneNotice" class="hint">{{ sceneNotice }}</div>

            <!-- card -->
            <div class="scene-block">
              <div class="scene-block__head">
                <h3>{{ t('memory.card') }}</h3>
                <span v-if="sceneCard" class="hint">
                  {{ t('memory.memoryCount', { n: sceneCard.memory_count }) }}
                </span>
              </div>
              <div v-if="!sceneCard" class="empty">{{ t('memory.sceneNoCard') }}</div>
              <div v-else class="stack">
                <div class="row">
                  <span class="hint">{{ t('memory.topics') }}</span>
                  <span v-for="topic in sceneCard.topics" :key="topic" class="tag">{{ topic }}</span>
                </div>
                <div v-if="sceneCard.people.length" class="row">
                  <span class="hint">{{ t('memory.people') }}</span>
                  <span v-for="person in sceneCard.people" :key="person" class="tag">
                    {{ person }}
                  </span>
                </div>
                <div>
                  <div class="hint">{{ t('memory.injectedPrompt') }}</div>
                  <pre class="scene-prompt">{{ sceneCard.prompt }}</pre>
                  <div class="hint">{{ t('memory.injectedHint') }}</div>
                </div>
              </div>
            </div>

            <!-- portrait -->
            <div class="scene-block">
              <div class="scene-block__head">
                <h3>{{ t('memory.portrait') }}</h3>
                <span v-if="scenePortrait" class="hint">
                  {{ t('memory.confidence') }} {{ confidencePct(scenePortrait.confidence) }}
                </span>
              </div>
              <div v-if="!scenePortrait" class="empty">{{ t('memory.sceneNoPortrait') }}</div>
              <div v-else class="stack">
                <div v-if="scenePortrait.headline" class="scene-headline">
                  {{ scenePortrait.headline }}
                </div>
                <div v-if="scenePortrait.themes.length" class="row">
                  <span class="hint">{{ t('memory.themes') }}</span>
                  <span v-for="theme in scenePortrait.themes" :key="theme" class="tag">
                    {{ theme }}
                  </span>
                </div>
                <div v-if="scenePortrait.tone" class="row">
                  <span class="hint">{{ t('memory.tone') }}</span>
                  <span class="tag">{{ scenePortrait.tone }}</span>
                </div>
                <div v-if="scenePortrait.recurring_questions.length" class="stack">
                  <span class="hint">{{ t('memory.questions') }}</span>
                  <ul class="scene-questions">
                    <li v-for="q in scenePortrait.recurring_questions" :key="q">{{ q }}</li>
                  </ul>
                </div>
                <div>
                  <div class="hint">{{ t('memory.injectedPrompt') }}</div>
                  <pre class="scene-prompt">{{ scenePortrait.prompt }}</pre>
                </div>
              </div>
            </div>

            <!-- skills -->
            <div class="scene-block">
              <div class="scene-block__head">
                <h3>{{ t('memory.skills') }}</h3>
                <span class="hint">{{ t('memory.skillsHint') }}</span>
              </div>

              <div v-if="skillError" class="error-banner">{{ skillError }}</div>
              <div v-if="skillNotice" class="hint">{{ skillNotice }}</div>

              <div v-if="skills.length === 0" class="empty">{{ t('memory.skillEmpty') }}</div>
              <ul v-else class="skill-list">
                <li v-for="skill in skills" :key="skill.skill_id" class="skill-item">
                  <div class="skill-item__head">
                    <strong>{{ skill.title }}</strong>
                    <span class="tag">{{ t('memory.skillSupport', { n: skill.support }) }}</span>
                    <span class="tag">{{ confidencePct(skill.confidence) }}</span>
                    <span class="strip__spacer" />
                    <button class="btn ghost" @click="removeSkill(skill)">
                      {{ t('common.delete') }}
                    </button>
                  </div>
                  <pre class="scene-prompt">{{ skill.body }}</pre>
                  <div class="hint">{{ t('memory.skillFile') }}: {{ skill.file }}</div>
                </li>
              </ul>

              <div class="scene-block__head">
                <h3>{{ t('memory.skillCandidates') }}</h3>
                <span class="hint">
                  {{ t('memory.skillCandidatesHint', { n: 3 }) }}
                </span>
              </div>
              <div v-if="candidates.length === 0" class="empty">
                {{ t('memory.skillNoCandidates') }}
              </div>
              <ul v-else class="candidate-list">
                <li v-for="c in candidates" :key="c.topic" class="candidate-item">
                  <span class="candidate-item__topic">{{ c.topic }}</span>
                  <span class="tag">{{ t('memory.skillSupport', { n: c.support }) }}</span>
                  <span class="strip__spacer" />
                  <button
                    class="btn ghost"
                    :disabled="generating === c.topic"
                    @click="createSkill(c.topic)"
                  >
                    {{ c.exists ? t('memory.skillRegenerate') : t('memory.skillCreate') }}
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
