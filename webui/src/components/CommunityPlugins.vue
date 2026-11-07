<script setup lang="ts">
/**
 * The community catalogue, rendered as a list of *claims*.
 *
 * There is no install button here on purpose. The index is a JSON file on someone else's
 * server; if a card in this list could install, then compromising that file would be
 * equivalent to running arbitrary code on every deployment, and the approval screen —
 * the one place a human reads the capability list — would become decoration. So this
 * panel answers "what exists and what is its latest version", and installation stays
 * where it was: download, upload, approve, per capability.
 */
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
import { useAsync } from '@/lib/useAsync'

const catalogue = useAsync(() => api.discoverPlugins())

const refreshing = ref(false)

const entries = computed(() => catalogue.data.value?.entries ?? [])
const blocked = computed<Record<string, string>>(() => catalogue.data.value?.blocked ?? {})
const available = computed(() => catalogue.data.value?.available ?? false)

/** A plugin is "blocked" if any of its listed versions is blocked. */
function blockedVersions(name: string, versions: string[]): { version: string; reason: string }[] {
  return versions
    .map((version) => ({ version, reason: blocked.value[`${name}@${version}`] ?? '' }))
    .filter((item) => item.reason !== '')
}

function isBlocked(name: string, versions: string[]): boolean {
  return blockedVersions(name, versions).length > 0
}

async function refresh(): Promise<void> {
  refreshing.value = true
  try {
    await catalogue.reload()
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <div class="stack">
    <div class="row" style="justify-content: space-between; align-items: baseline">
      <p class="hint" style="margin: 0">{{ t('plugins.communityNote') }}</p>
      <button class="btn ghost" type="button" :disabled="refreshing" @click="refresh">
        {{ t('plugins.refreshIndex') }}
      </button>
    </div>

    <!-- Three distinct states, because "cannot discover" and "nothing listed" need
         different actions from the operator: one is a network/config problem, the other
         is simply an empty catalogue. Collapsing them into one message hides that. -->
    <div v-if="!available && catalogue.data.value?.error" class="error-banner">
      {{ t('plugins.discoverUnavailable', { reason: catalogue.data.value.error }) }}
    </div>
    <div v-else-if="!available" class="empty">{{ t('plugins.discoverNoIndex') }}</div>
    <div v-else-if="!entries.length" class="empty">{{ t('plugins.discoverEmpty') }}</div>

    <div v-else class="cards">
      <article
        v-for="entry in entries"
        :key="entry.name"
        class="card"
        :class="{ 'card--muted': isBlocked(entry.name, entry.versions) }"
      >
        <header class="card__head">
          <h3>{{ entry.name }}</h3>
          <span class="tag">{{ t('plugins.latest') }} {{ entry.latest || '—' }}</span>
        </header>

        <p class="card__summary">{{ entry.summary || '—' }}</p>

        <dl class="card__meta">
          <div>
            <dt>{{ t('plugins.versions') }}</dt>
            <dd class="mono">{{ entry.versions.join(', ') || '—' }}</dd>
          </div>
          <div v-if="entry.author">
            <dt>{{ t('plugins.trust') }}</dt>
            <dd>{{ entry.author }}</dd>
          </div>
        </dl>

        <!-- Blocked versions are called out on the card itself. A blocked version that
             only appears in a details dialog is one an operator will try to install. -->
        <div
          v-for="item in blockedVersions(entry.name, entry.versions)"
          :key="item.version"
          class="card__blocked"
        >
          <span class="tag bad">{{ t('plugins.blockedVersion') }} {{ item.version }}</span>
          <span class="hint">{{ t('plugins.blockedReason', { reason: item.reason }) }}</span>
          <!-- Says what will actually happen, not just that the version is listed as
               bad. The install path refuses it server-side, so an operator who reads
               only "Blocked" and then uploads the package gets a rejection with no
               warning that this card already knew. -->
          <span class="hint">{{ t('plugins.blockedInstall') }}</span>
        </div>

        <p class="hint" style="margin: 0">{{ t('plugins.communityHint') }}</p>
      </article>
    </div>

    <p v-if="catalogue.data.value?.source" class="hint" style="margin: 0">
      {{ t('plugins.source') }}: <span class="mono">{{ catalogue.data.value.source }}</span>
    </p>
  </div>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

/* Desaturated rather than hidden: an operator who already installed a blocked version
   still needs to find it in this list to read why. */
.card--muted {
  opacity: 0.72;
}

.card__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.card__head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
}

.card__summary {
  margin: 0;
  color: var(--ink-2);
}

.card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin: 0;
}

.card__meta div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.card__meta dt {
  color: var(--ink-3);
  font-size: 11px;
}

.card__meta dd {
  margin: 0;
  color: var(--ink-2);
}

.card__blocked {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: var(--danger-soft);
  border-radius: 8px;
}
</style>
