<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import { t } from '@/i18n'
import { useAsync } from '@/lib/useAsync'

/**
 * Plugin package install: the one page where a package arrives from outside.
 *
 * The page is built around a single distinction the backend enforces and the UI must
 * not blur: **installing is not approving**. Uploading writes bytes and makes the
 * plugin discoverable; approving grants named capabilities one at a time. If the
 * cards showed a single "启用" button, the distinction would exist only in the API
 * and an operator would reasonably read "installed" as "running".
 */
const router = useRouter()
const listing = useAsync(() => api.plugins())

const plugins = computed<any[]>(() => listing.data.value?.installed ?? [])
const pending = computed(() => plugins.value.filter((p) => !p.approved).length)
const live = computed(() => plugins.value.filter((p) => p.loaded).length)

const uploading = ref(false)
const dragging = ref(false)
const uploadError = ref('')
const uploadedHere = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

/** Capability risk tiers. Colour never carries the meaning alone: each tag also
 *  prints the tier in text, so the page works without colour perception. */
const HIGH = new Set(['http', 'command', 'cron', 'network', 'exec'])
const MID = new Set(['storage', 'send', 'memory_write', 'write', 'kb_write'])

function tier(cap: string): 'high' | 'mid' | 'low' {
  const name = cap.toLowerCase()
  if (HIGH.has(name)) return 'high'
  if (MID.has(name)) return 'mid'
  return 'low'
}

function tierClass(cap: string): string {
  const level = tier(cap)
  return level === 'high' ? 'tag bad' : level === 'mid' ? 'tag lamp' : 'tag'
}

function tierWord(cap: string): string {
  const level = tier(cap)
  if (level === 'high') return t('market.tierHigh')
  return level === 'mid' ? t('market.tierMid') : t('market.tierLow')
}

async function upload(file: File): Promise<void> {
  uploading.value = true
  uploadError.value = ''
  try {
    const result = await api.installPlugin(file)
    uploadedHere.value = [result.name, ...uploadedHere.value.filter((n) => n !== result.name)]
    await listing.reload()
  } catch (err) {
    uploadError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    uploading.value = false
  }
}

function onFileChosen(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void upload(file)
  input.value = ''
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void upload(file)
}

function openPlugins(): void {
  // Approval lives on the plugin page; sending the operator there is the point of
  // the second action, not a convenience.
  void router.push({ name: 'plugins' })
}
</script>

<template>
  <div class="warn-banner">
    {{ t('market.banner') }}
  </div>

  <div v-if="uploadError" class="error-banner">{{ uploadError }}</div>

  <section class="strip">
    <span class="strip__title">{{ t('market.title') }}</span>
    <span class="strip__spacer" />
    <span class="hint">{{ t('market.digestNote') }}</span>
  </section>

  <div class="grid cols-3">
    <div class="readout">
      <span class="readout__label">{{ t('common.installed') }}</span>
      <span class="readout__value">{{ plugins.length }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('market.pendingApproval') }}</span>
      <span class="readout__value">{{ pending }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">{{ t('market.live') }}</span>
      <span class="readout__value">{{ live }}</span>
    </div>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('market.upload') }}</h2>
      <span class="strip__spacer" />
      <span class="hint">{{ t('market.zipOnly') }}</span>
    </div>
    <div class="panel__body stack">
      <div
        class="row"
        style="justify-content: space-between; gap: 16px"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <div class="stack" style="gap: 4px">
          <strong>{{ dragging ? t('market.dropNow') : t('market.dropHere') }}</strong>
          <span class="faint">
            {{ t('market.verifyOrder') }}
          </span>
        </div>
        <button class="btn lamp" :disabled="uploading" @click="fileInput?.click()">
          {{ uploading ? t('market.installing') : t('market.chooseFile') }}
        </button>
        <input
          ref="fileInput"
          class="visually-hidden"
          type="file"
          accept=".zip,application/zip"
          @change="onFileChosen"
        />
      </div>

      <div class="row" style="gap: 12px">
        <span class="hint">{{ t('market.riskLegend') }}</span>
        <span class="tag bad">{{ t('market.tierHigh') }}</span>
        <span class="hint">{{ t('market.tierHighWhy') }}</span>
        <span class="tag lamp">{{ t('market.tierMid') }}</span>
        <span class="hint">{{ t('market.tierMidWhy') }}</span>
        <span class="tag">{{ t('market.tierLow') }}</span>
        <span class="hint">{{ t('market.tierLowWhy') }}</span>
      </div>

      <p v-if="uploadedHere.length" class="hint">
        {{ t('market.installedNow', { names: uploadedHere.join(t('common.listSep')) }) }}
      </p>
    </div>
  </section>

  <section v-if="plugins.length" class="grid cols-2">
    <article v-for="plugin in plugins" :key="plugin.name" class="panel">
      <div class="panel__head">
        <h2>{{ plugin.name }}</h2>
        <span class="tag">{{ plugin.version || '0.0.0' }}</span>
        <span class="strip__spacer" />
        <span class="tag" :class="plugin.trust === 'trusted' ? 'ok' : 'bad'">
          {{ plugin.trust === 'trusted' ? t('plugins.trusted') : t('plugins.untrusted') }}
        </span>
      </div>
      <div class="panel__body stack">
        <p class="faint" style="margin: 0">
          {{ plugin.description || t('market.noDescription') }}
        </p>

        <div class="row" style="flex-wrap: wrap; gap: 6px">
          <span v-if="!plugin.capabilities?.length" class="faint">{{ t('market.noCapabilities') }}</span>
          <span
            v-for="cap in plugin.capabilities"
            :key="cap"
            :class="tierClass(cap)"
            :title="t('market.riskTitle', { tier: tierWord(cap) })"
          >
            {{ cap }} · {{ tierWord(cap) }}
          </span>
        </div>

        <div class="row">
          <span class="pill" :class="plugin.approved ? 'ok' : 'warn'">
            <i class="dot" />{{ plugin.approved ? t('market.approved') : t('market.pendingApproval') }}
          </span>
          <span class="pill" :class="plugin.loaded ? 'ok' : ''">
            <i class="dot" />{{ plugin.loaded ? t('market.live') : t('plugins.notLoaded') }}
          </span>
          <span class="strip__spacer" />
          <button class="btn ghost" @click="openPlugins()">
            {{ plugin.approved ? t('market.view') : t('market.goApprove') }}
          </button>
        </div>

        <p v-if="plugin.pending?.length" class="hint" style="margin: 0">
          {{ t('market.notYetGranted', { names: plugin.pending.join(t('common.listSep')) }) }}
        </p>
      </div>
    </article>
  </section>

  <section v-else class="panel">
    <div class="panel__head"><h2>{{ t('market.empty') }}</h2></div>
    <div class="panel__body">
      <div class="empty">
        <p>{{ t('market.emptyLead') }}</p>
        <pre class="mono" style="margin: 0; white-space: pre-wrap">data/plugins/
└── demo/
    ├── plugin.yaml   # name / version / entry / capabilities
    └── main.py</pre>
        <p class="hint">
          {{ t('market.emptyTail') }}
        </p>
      </div>
    </div>
  </section>
</template>
