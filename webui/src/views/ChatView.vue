<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, chatApi, type ChatAccount, type ChatMessage, type ChatSessionRow } from '@/api/client'
import MessageBubble from '@/components/chat/MessageBubble.vue'
import NoteComposer from '@/components/chat/NoteComposer.vue'
import { t } from '@/i18n'

const router = useRouter()

const me = ref<ChatAccount | null>(null)
const surfaces = ref<{ talk: boolean }>({ talk: false })
const sessions = ref<ChatSessionRow[]>([])
const scope = ref<'all' | 'member'>('member')
const activeKey = ref('')
const messages = ref<ChatMessage[]>([])
const cursor = ref(0)
const hasOlder = ref(false)
const loadingSessions = ref(true)
const loadingMessages = ref(false)
const loadingEarlier = ref(false)
const saving = ref(false)
const error = ref('')
const noteError = ref('')
const query = ref('')
const onlyMine = ref(true)
const detailOpen = ref(false)
const unread = ref(0)

const scroller = ref<HTMLElement | null>(null)
let source: EventSource | null = null
let pendingId = -1
let sessionsTimer: ReturnType<typeof setInterval> | null = null

/** This account's conversation session; empty when talk is off. */
const talkKey = computed(() =>
  me.value && surfaces.value.talk ? `web:private:account-${me.value.id}` : '',
)
const isTalkSession = computed(() => activeKey.value !== '' && activeKey.value === talkKey.value)

const visibleSessions = computed(() => {
  const needle = query.value.trim().toLowerCase()
  const allowed = new Set(me.value?.sessions ?? [])
  return sessions.value.filter((row) => {
    if (onlyMine.value && scope.value === 'member' && allowed.size > 0) {
      if (!allowed.has(row.session_key)) return false
    }
    if (!needle) return true
    return (
      row.session_key.toLowerCase().includes(needle) ||
      sessionLabel(row.session_key).toLowerCase().includes(needle)
    )
  })
})

const activeSession = computed(
  () => sessions.value.find((row) => row.session_key === activeKey.value) ?? null,
)

/** `qq:group:12345` reads as `群 12345`; the talk session gets its own name. */
function sessionLabel(key: string): string {
  if (talkKey.value && key === talkKey.value) return t('chat.session.webTalk')
  const [platform, kind, ...rest] = key.split(':')
  const id = rest.join(':')
  if (!platform || !kind || !id) return key
  if (kind === 'group') return `群 ${id}`
  if (kind === 'private' || kind === 'c2c') return `私聊 ${id}`
  return key
}

function sessionTime(seconds: number): string {
  if (!seconds) return ''
  const date = new Date(seconds * 1000)
  const today = new Date()
  const sameDay =
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  return sameDay
    ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(date)
    : new Intl.DateTimeFormat(undefined, { month: '2-digit', day: '2-digit' }).format(date)
}

async function scrollToBottom(smooth = false): Promise<void> {
  await nextTick()
  const el = scroller.value
  if (!el) return
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollTo({ top: el.scrollHeight, behavior: smooth && !reduced ? 'smooth' : 'auto' })
}

function closeStream(): void {
  source?.close()
  source = null
}

function openStream(): void {
  closeStream()
  if (!activeKey.value) return
  source = new EventSource(chatApi.streamUrl(activeKey.value, cursor.value))
  source.onmessage = (event) => {
    try {
      const row = JSON.parse(event.data) as ChatMessage
      if (row.session_key !== activeKey.value) return
      if (row.id <= cursor.value && row.id > 0) return
      messages.value.push(row)
      if (row.id > 0) cursor.value = row.id
      if (document.hidden) unread.value += 1
      void scrollToBottom(true)
    } catch {
      // ignored: a malformed frame is dropped; the next poll replays from the same cursor.
    }
  }
  source.onerror = () => {
    // EventSource retries on its own; closing here would turn a transient proxy
    // restart into a permanently dead stream until the user reloads.
  }
}

async function openSession(key: string): Promise<void> {
  if (activeKey.value === key && messages.value.length > 0) {
    detailOpen.value = true
    return
  }
  activeKey.value = key
  detailOpen.value = true
  messages.value = []
  cursor.value = 0
  hasOlder.value = false
  loadingMessages.value = true
  error.value = ''
  unread.value = 0
  closeStream()
  try {
    // `latest`, not `after_id: 0`: the first screen of an old session must show the
    // newest page. The forward cursor only answers "what arrived since N", which is
    // the wrong question for a session with months of history.
    const page = await chatApi.messages(key, { latest: true, limit: 100 })
    messages.value = page.messages
    const last = page.messages[page.messages.length - 1]
    cursor.value = last ? last.id : 0
    hasOlder.value = page.has_older ?? false
    await scrollToBottom()
    openStream()
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await router.replace({ path: '/chat/login', query: { next: '/chat' } })
      return
    }
    error.value = err instanceof Error ? err.message : t('chat.messages.error')
  } finally {
    loadingMessages.value = false
  }
}

async function loadEarlier(): Promise<void> {
  if (loadingEarlier.value || !activeKey.value || messages.value.length === 0) return
  loadingEarlier.value = true
  const el = scroller.value
  const heightBefore = el?.scrollHeight ?? 0
  try {
    const page = await chatApi.messages(activeKey.value, {
      beforeId: messages.value[0]?.id,
      limit: 100,
    })
    messages.value = [...page.messages, ...messages.value]
    hasOlder.value = page.has_older ?? false
    await nextTick()
    if (el) el.scrollTop = el.scrollHeight - heightBefore
  } catch {
    noteError.value = t('chat.messages.error')
  } finally {
    loadingEarlier.value = false
  }
}

/** Sync the tail after a talk POST: both the user row and the reply are archived by
 * the pipeline, and one forward page replaces the optimistic bubble with real ids. */
async function syncTail(key: string): Promise<void> {
  const page = await chatApi.messages(key, { afterId: cursor.value, limit: 100 })
  if (key !== activeKey.value) return
  for (const row of page.messages) {
    if (row.id > cursor.value) {
      messages.value.push(row)
      cursor.value = row.id
    }
  }
}

async function sendTalk(text: string): Promise<void> {
  const key = talkKey.value
  if (!key) return
  saving.value = true
  noteError.value = ''
  const optimistic: ChatMessage = {
    id: pendingId--,
    session_key: key,
    role: 'user',
    content: text,
    adapter: 'web',
    user_name: me.value?.username ?? '',
    created_at: Date.now() / 1000,
  }
  messages.value.push(optimistic)
  await scrollToBottom(true)
  try {
    const result = await chatApi.talk(text)
    messages.value = messages.value.filter((row) => row.id !== optimistic.id)
    await syncTail(key)
    if (!result.reply) noteError.value = t('chat.talk.refused')
    void scrollToBottom(true)
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      messages.value = messages.value.filter((row) => row.id !== optimistic.id)
      await router.replace({ path: '/chat/login', query: { next: '/chat' } })
      return
    }
    messages.value = messages.value.filter((row) => row.id !== optimistic.id)
    noteError.value = err instanceof Error ? err.message : t('chat.talk.refused')
  } finally {
    saving.value = false
  }
}

async function refreshSessions(): Promise<void> {
  if (loadingSessions.value) return
  try {
    const result = await chatApi.sessions()
    sessions.value = result.sessions
    scope.value = result.scope
  } catch {
    // degraded: a missed poll leaves the previous list in place; the next one retries.
  }
}

async function bootstrap(): Promise<void> {
  loadingSessions.value = true
  error.value = ''
  try {
    me.value = await chatApi.me()
    try {
      surfaces.value = await chatApi.surfaces()
    } catch {
      // fallback: an old backend without /surfaces still serves the archive; only talk hides.
    }
    const result = await chatApi.sessions()
    sessions.value = result.sessions
    scope.value = result.scope
    const first = sessions.value[0]
    if (first) await openSession(first.session_key)
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await router.replace({ path: '/chat/login', query: { next: '/chat' } })
      return
    }
    error.value = err instanceof Error ? err.message : t('chat.messages.error')
  } finally {
    loadingSessions.value = false
  }
}

async function saveNote(text: string): Promise<void> {
  if (!activeKey.value) return
  saving.value = true
  noteError.value = ''
  const optimistic: ChatMessage = {
    id: pendingId--,
    session_key: activeKey.value,
    role: 'note',
    content: text,
    adapter: 'web',
    user_name: me.value?.username ?? '',
    created_at: Date.now() / 1000,
  }
  messages.value.push(optimistic)
  await scrollToBottom(true)
  try {
    const result = await chatApi.note(activeKey.value, text)
    const index = messages.value.findIndex((row) => row.id === optimistic.id)
    if (index >= 0) messages.value.splice(index, 1, result.note)
    if (result.note.id > cursor.value) cursor.value = result.note.id
  } catch (err) {
    messages.value = messages.value.filter((row) => row.id !== optimistic.id)
    noteError.value = err instanceof Error ? err.message : t('chat.messages.error')
  } finally {
    saving.value = false
  }
}

async function logout(): Promise<void> {
  closeStream()
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
  } catch {
    // fallback: local sign-out is best effort; the cookie may already be gone.
  }
  await router.replace('/chat/login')
}

onMounted(() => {
  void bootstrap()
  // The list is derived from the archive, so a new session appears only when it has
  // messages — poll at the same pace the SSE poll implies, keeping the selection.
  sessionsTimer = setInterval(() => {
    void refreshSessions()
  }, 30_000)
})

onBeforeUnmount(() => {
  closeStream()
  if (sessionsTimer !== null) clearInterval(sessionsTimer)
})
</script>

<template>
  <div class="chat" :class="{ 'chat--detail': detailOpen }">
    <aside class="chat__list" :aria-label="t('chat.sessions')">
      <header class="chat__listhead">
        <div>
          <p class="chat__mark">ARCHIVE</p>
          <h1>{{ t('chat.title') }}</h1>
        </div>
        <button type="button" class="chat__logout" @click="logout">{{ t('chat.logout') }}</button>
      </header>
      <p class="chat__lede">{{ t('chat.subtitle') }}</p>

      <div class="chat__filters">
        <label class="chat__search">
          <span class="chat__sronly">{{ t('chat.search') }}</span>
          <input v-model="query" type="search" :placeholder="t('chat.search')" />
        </label>
        <label class="chat__check">
          <input v-model="onlyMine" type="checkbox" />
          <span>{{ t('chat.onlyMine') }}</span>
        </label>
      </div>

      <p v-if="loadingSessions" class="chat__muted">{{ t('chat.messages.loading') }}</p>

      <div v-else-if="visibleSessions.length === 0" class="chat__empty">
        <p>{{ t('chat.sessions.empty') }}</p>
        <p class="chat__muted">{{ t('chat.sessions.emptyHint') }}</p>
      </div>

      <ul v-else class="sessions">
        <li v-for="row in visibleSessions" :key="row.session_key">
          <button
            type="button"
            class="sessions__row"
            :class="{ 'is-active': row.session_key === activeKey }"
            :aria-current="row.session_key === activeKey ? 'true' : undefined"
            @click="openSession(row.session_key)"
          >
            <span class="sessions__name">{{ sessionLabel(row.session_key) }}</span>
            <span class="sessions__meta">
              <span>{{ row.message_count }}</span>
              <time>{{ sessionTime(row.last_at) }}</time>
            </span>
            <span class="sessions__key">{{ row.session_key }}</span>
          </button>
        </li>
      </ul>
    </aside>

    <section class="chat__main">
      <header class="chat__mainhead">
        <button
          v-if="activeKey"
          type="button"
          class="chat__back"
          @click="detailOpen = false"
        >
          ← {{ t('chat.back') }}
        </button>
        <div class="chat__who">
          <h2>{{ activeKey ? sessionLabel(activeKey) : t('chat.sessions') }}</h2>
          <p v-if="activeKey" class="chat__keyline">{{ activeKey }}</p>
        </div>
        <span class="chat__scope">
          {{ scope === 'all' ? t('chat.info.scopeAll') : t('chat.info.scopeMember') }}
        </span>
      </header>

      <div ref="scroller" class="chat__log" role="log" aria-live="polite">
        <p v-if="loadingMessages" class="chat__placeholder">{{ t('chat.messages.loading') }}</p>

        <div v-else-if="error" class="chat__placeholder">
          <p>{{ t('chat.messages.error') }}</p>
          <p class="chat__muted">{{ error }}</p>
          <button type="button" class="chat__retry" @click="activeKey && openSession(activeKey)">
            {{ t('chat.retry') }}
          </button>
        </div>

        <div v-else-if="!activeKey || messages.length === 0" class="chat__placeholder">
          <p>{{ t('chat.messages.empty') }}</p>
          <p class="chat__muted">{{ t('chat.subtitle') }}</p>
        </div>

        <template v-else>
          <button
            v-if="hasOlder"
            type="button"
            class="chat__earlier"
            :disabled="loadingEarlier"
            @click="loadEarlier"
          >
            {{ loadingEarlier ? t('chat.loadEarlier.loading') : t('chat.loadEarlier') }}
          </button>
          <MessageBubble
            v-for="row in messages"
            :key="row.id"
            :message="row"
            :pending="row.id < 0"
          />
          <p v-if="unread > 0" class="chat__unread" aria-live="polite">
            {{ t('chat.newMessages') }} · {{ unread }}
          </p>
        </template>
      </div>

      <p v-if="noteError" class="chat__noteerror" role="alert">{{ noteError }}</p>

      <NoteComposer
        :disabled="!activeKey || loadingMessages"
        :saving="saving"
        :mode="isTalkSession ? 'talk' : 'note'"
        @submit="isTalkSession ? sendTalk($event) : saveNote($event)"
      />
    </section>

    <aside v-if="activeKey" class="chat__info">
      <h2>{{ t('chat.info.title') }}</h2>
      <dl>
        <dt>{{ t('chat.info.key') }}</dt>
        <dd class="chat__mono">{{ activeKey }}</dd>
        <dt>{{ t('chat.info.count') }}</dt>
        <dd>{{ activeSession?.message_count ?? messages.length }}</dd>
        <dt>{{ t('chat.info.scope') }}</dt>
        <dd>{{ scope === 'all' ? t('chat.info.scopeAll') : t('chat.info.scopeMember') }}</dd>
        <dt>{{ t('chat.role.note') }}</dt>
        <dd>{{ messages.filter((row) => row.role === 'note').length }}</dd>
      </dl>
      <p class="chat__muted chat__infonote">{{ t('chat.composer.notice') }}</p>
    </aside>
  </div>
</template>

<style scoped>
.chat {
  display: grid;
  grid-template-columns: 1fr;
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
}

.chat__list {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  padding: 16px 14px;
  border-right: 1px solid var(--border);
  background: var(--surface);
}

.chat__listhead {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.chat__mark {
  margin: 0 0 4px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  color: var(--brand);
}

.chat__listhead h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.chat__logout {
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--surface-2);
  color: var(--ink-3);
  font: inherit;
  font-size: 11px;
  padding: 5px 8px;
  cursor: pointer;
}

.chat__logout:hover {
  border-color: var(--border-strong);
  color: var(--ink);
}

.chat__lede {
  margin: 8px 0 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-3);
}

.chat__filters {
  display: grid;
  gap: 7px;
  margin-bottom: 10px;
}

.chat__search input {
  width: 100%;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2);
  color: var(--ink);
  font: inherit;
  font-size: 12px;
}

.chat__search input:focus-visible {
  border-color: var(--brand);
  outline: none;
  box-shadow: 0 0 0 3px var(--brand-soft);
}

.chat__check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--ink-3);
}

.chat__sronly {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.sessions {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-y: auto;
}

.sessions__row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 2px 8px;
  width: 100%;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease;
}

.sessions__row:hover {
  background: var(--surface-3);
}

.sessions__row.is-active {
  border-color: var(--brand-line);
  background: var(--brand-soft);
}

.sessions__row:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 1px;
}

.sessions__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}

.sessions__meta {
  display: flex;
  gap: 8px;
  font-size: 10px;
  color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}

.sessions__key {
  grid-column: 1 / -1;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat__main {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-width: 0;
  background: var(--bg);
}

.chat__mainhead {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  backdrop-filter: blur(8px);
}

.chat__back {
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--surface);
  color: var(--ink-2);
  font: inherit;
  font-size: 11px;
  padding: 5px 8px;
  cursor: pointer;
}

.chat__who {
  min-width: 0;
}

.chat__who h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat__keyline {
  margin: 1px 0 0;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat__scope {
  margin-left: auto;
  padding: 3px 8px;
  border: 1px solid var(--idle-line);
  border-radius: 999px;
  background: var(--surface);
  font-size: 10px;
  color: var(--ink-3);
  white-space: nowrap;
}

.chat__log {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.chat__placeholder {
  margin: auto;
  max-width: 34ch;
  text-align: center;
  color: var(--ink-2);
  font-size: 13px;
}

.chat__placeholder .chat__muted {
  margin-top: 4px;
}

.chat__muted {
  color: var(--ink-3);
  font-size: 11px;
  line-height: 1.5;
}

.chat__retry {
  margin-top: 8px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  background: var(--surface);
  color: var(--ink);
  font: inherit;
  font-size: 12px;
  padding: 5px 12px;
  cursor: pointer;
}

.chat__earlier {
  align-self: center;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
  background: var(--surface);
  color: var(--ink-2);
  font: inherit;
  font-size: 11px;
  padding: 4px 12px;
  cursor: pointer;
}

.chat__earlier:hover:not(:disabled) {
  border-color: var(--brand);
  color: var(--ink);
}

.chat__earlier:disabled {
  color: var(--ink-3);
  cursor: default;
}

.chat__empty {
  padding: 14px 10px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius);
  text-align: center;
  font-size: 12px;
}

.chat__empty p {
  margin: 0;
}

.chat__unread {
  align-self: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--brand);
  color: var(--on-brand);
  font-size: 10px;
}

.chat__noteerror {
  margin: 0;
  padding: 6px 14px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 11px;
}

.chat__info {
  display: none;
  padding: 16px 14px;
  border-left: 1px solid var(--border);
  background: var(--surface);
  font-size: 12px;
}

.chat__info h2 {
  margin: 0 0 10px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-3);
}

.chat__info dl {
  display: grid;
  gap: 2px;
  margin: 0;
}

.chat__info dt {
  margin-top: 8px;
  font-size: 10px;
  color: var(--ink-3);
}

.chat__info dd {
  margin: 0;
  font-size: 12px;
  color: var(--ink);
}

.chat__mono {
  font-family: var(--mono);
  font-size: 10px;
  overflow-wrap: anywhere;
}

.chat__infonote {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

@media (min-width: 960px) {
  .chat {
    grid-template-columns: 300px minmax(0, 1fr);
    height: 100vh;
  }

  .chat__list,
  .chat__main {
    min-height: 0;
    height: 100vh;
  }

  .chat__back {
    display: none;
  }
}

@media (min-width: 1280px) {
  .chat {
    grid-template-columns: 300px minmax(0, 1fr) 260px;
  }

  .chat__info {
    display: block;
    height: 100vh;
    overflow-y: auto;
  }
}

/* Mobile: one pane at a time. The list is the home; opening a session swaps panes. */
@media (max-width: 959px) {
  .chat__main {
    display: none;
  }

  .chat--detail .chat__list {
    display: none;
  }

  .chat--detail .chat__main {
    display: flex;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sessions__row {
    transition: none;
  }
}
</style>
