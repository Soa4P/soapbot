<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
import { useAsync } from '@/lib/useAsync'

/**
 * First-run checklist: "what is still missing before this bot answers a message".
 *
 * Every failure mode this project has shipped with was silent: a green panel with zero
 * providers ("the model stage is disabled"), zero adapters ("the service is up and will
 * never receive a message"), a startup error in a corner of the runtime page, a read-only
 * config directory ("saved" but not in effect). None of them raised anything an operator
 * would notice. This card is the one place that says, plainly, which of the four is true.
 *
 * No new backend: all five answers already exist in `/api/runtime`, `/api/providers` and
 * `/api/settings`. Adding a dedicated endpoint would have meant a second implementation of
 * "is it configured", and the two would eventually disagree.
 *
 * Two ways to stop seeing it — all-green (automatic, because a checklist that outlives its
 * usefulness is clutter) or dismissed (remembered in `localStorage`, next to the language
 * preference: it is a browser-local UI choice, not deployment state, and does not belong in
 * the server's config).
 */
const DISMISS_KEY = 'soapbot.setup.dismissed'

const runtime = useAsync(() => api.runtime())
const providers = useAsync(() => api.providers())
const info = useAsync(() => api.settings())

const dismissed = ref(readDismissed())

function readDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    // Private mode. Showing the card again is the safe failure: the alternative is a
    // feature that silently disappears for one browser profile.
    return false
  }
}

function dismiss(): void {
  dismissed.value = true
  try {
    localStorage.setItem(DISMISS_KEY, '1')
  } catch {
    /* the card stays hidden for this session only, which is fine */
  }
}

const providerCount = computed(() => (providers.data.value?.providers ?? []).length)

const adapters = computed<any[]>(() => {
  const map = runtime.data.value?.adapters ?? {}
  return Object.values(map) as any[]
})

const startupErrors = computed<string[]>(() => runtime.data.value?.startup_errors ?? [])

const configDir = computed<string>(() => info.data.value?.config_dir ?? '')
const configWritable = computed(() => info.data.value?.config_dir_writable === true)

interface Item {
  key: string
  ok: boolean
  label: string
  detail: string
  to: string
}

/**
 * Built in a computed rather than at module scope so switching language re-renders the
 * labels — a module-level array freezes them at import time (the same trap the overview's
 * flag list documents).
 */
const items = computed<Item[]>(() => [
  {
    key: 'providers',
    ok: providerCount.value > 0,
    label: t('setup.providers'),
    detail: providerCount.value
      ? t('setup.providersOk', { n: providerCount.value })
      : t('setup.providersMissing'),
    to: '/config',
  },
  {
    key: 'adapters',
    ok: adapters.value.length > 0,
    label: t('setup.adapters'),
    detail: adapters.value.length
      ? t('setup.adaptersOk', { n: adapters.value.length })
      : t('setup.adaptersMissing'),
    to: '/config',
  },
  {
    key: 'online',
    ok: adapters.value.some((adapter) => adapter.online),
    label: t('setup.online'),
    detail: adapters.value.some((adapter) => adapter.online)
      ? t('setup.onlineOk')
      : t('setup.onlineMissing'),
    to: '/runtime',
  },
  {
    key: 'startup',
    ok: startupErrors.value.length === 0,
    label: t('setup.startup'),
    detail: startupErrors.value.length
      ? t('setup.startupMissing', { n: startupErrors.value.length })
      : t('setup.startupOk'),
    to: '/runtime',
  },
  {
    key: 'writable',
    ok: configWritable.value,
    label: t('setup.writable'),
    detail: configWritable.value
      ? t('setup.writableOk', { path: configDir.value })
      : t('setup.writableMissing', { path: configDir.value }),
    to: '/settings',
  },
])

/* ------------------------------------------------------------------ the beginner path */
/*
 * The checklist answers "what is still missing". Someone who has never deployed anything
 * needs a different question answered — "what do I do, in order, with my hands" — and the
 * two are not the same list: the checklist has five rows, three of which only make sense
 * once the first two are done.
 *
 * `ws://127.0.0.1:3001` is the value NapCat's own "WebSocket server" listens on by default,
 * which makes forward mode the only address a beginner can use without changing anything
 * in NapCat. It is here, copyable, instead of buried in a table row on another page.
 */
const NAPCAT_DEFAULT = 'ws://127.0.0.1:3001'
const copied = ref(false)

async function copyAddress(): Promise<void> {
  try {
    await navigator.clipboard.writeText(NAPCAT_DEFAULT)
    copied.value = true
    window.setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    // Clipboard needs a secure context; the text is on screen and selectable either way.
    copied.value = false
  }
}

const failed = computed(() => items.value.filter((item) => !item.ok).length)
const passed = computed(() => items.value.length - failed.value)

/**
 * Hidden when everything passes — the card has done its job, and leaving five green rows
 * at the top of the page forever trains people to stop reading it.
 */
const visible = computed(() => !dismissed.value && failed.value > 0)
</script>

<template>
  <section v-if="visible" class="panel">
    <div class="panel__head">
      <h2>{{ t('setup.title') }}</h2>
      <span class="tag" :class="failed ? 'bad' : 'ok'">{{ passed }}/{{ items.length }}</span>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" @click="dismiss">{{ t('setup.dismiss') }}</button>
    </div>
    <div class="panel__body">
      <p class="hint" style="margin: 0 0 10px">{{ t('setup.hint') }}</p>

      <!-- Before the checklist, because a checklist tells you what is wrong and this tells
           you what to do with your hands. The address is copyable here so a first-time
           operator does not have to find it in a table on another page. -->
      <div class="steps">
        <h3>{{ t('setup.stepsTitle') }}</h3>
        <ol>
          <li>{{ t('setup.step1') }}</li>
          <li>
            {{ t('setup.step2') }}
            <span class="steps__addr">
              <code>{{ NAPCAT_DEFAULT }}</code>
              <button class="btn ghost" type="button" @click="copyAddress">
                {{ copied ? t('setup.copied') : t('setup.copy') }}
              </button>
            </span>
          </li>
          <li>{{ t('setup.step3') }}</li>
        </ol>
      </div>
      <ul class="setup">
        <li v-for="item in items" :key="item.key" class="setup__item">
          <span class="pill" :class="item.ok ? 'ok' : 'bad'">
            <i class="dot" />{{ item.ok ? t('setup.ok') : t('setup.todo') }}
          </span>
          <span class="setup__text">
            <span class="setup__label">{{ item.label }}</span>
            <span class="hint">{{ item.detail }}</span>
          </span>
          <RouterLink v-if="!item.ok" class="btn ghost" :to="item.to">
            {{ t('setup.go') }}
          </RouterLink>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.setup {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 2px;
}

/* Hairlines instead of cards: five stacked boxes at the top of a page reads as five
   alarms, and four of these are usually fine. */
.setup__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid var(--border);
}

.setup__item:first-child {
  border-top: 0;
  padding-top: 0;
}

.setup__text {
  display: grid;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.setup__label {
  font-size: 13px;
}

.steps {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2);
  padding: 10px 14px;
  margin: 0 0 12px;
}
.steps h3 {
  margin: 0 0 4px;
  font-size: 0.95rem;
}
.steps ol {
  margin: 4px 0 0 20px;
  padding: 0;
}
.steps li {
  margin: 6px 0;
}
.steps__addr {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 6px;
}
.steps__addr code {
  font-family: var(--mono);
  user-select: all;
}

/* The path and the count are the actionable part; keep them from pushing the button
   off the row when a long mount path is reported. */
.hint {
  overflow-wrap: anywhere;
}
</style>
