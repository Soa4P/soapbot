<script setup lang="ts">
import { ref, watch } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'

/**
 * Persona avatar (page 07, expanded persona row) — **placeholder renderer**.
 *
 * The server side is real: the model directory is discovered, validated and served with
 * containment and an extension allowlist. What is missing is the Cubism runtime, and
 * pretending otherwise would be worse than saying so — an operator who drops in a model
 * and sees a still image with no explanation concludes the feature is broken.
 *
 * So this shows: the declared model, its motion groups and expressions, and the first
 * texture as a static preview. When a renderer is added later, only this component
 * changes; the API contract (`available`, `motions`, `textures`, asset endpoint) does not.
 */
const props = defineProps<{ personaId: string }>()

interface AvatarInfo {
  available: boolean
  reason?: string
  model?: string
  motions?: Record<string, string[]>
  expressions?: string[]
  textures?: string[]
  preview?: string
  assets?: number
  bytes?: number
  renderer?: string
  hint?: string
}

const info = ref<AvatarInfo | null>(null)
const error = ref('')
const loading = ref(false)

async function load(): Promise<void> {
  if (!props.personaId) return
  loading.value = true
  error.value = ''
  try {
    info.value = await api.personaAvatar(props.personaId)
  } catch (err) {
    error.value = (err as Error).message
    info.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.personaId, load, { immediate: true })

function assetUrl(relative: string): string {
  return `/api/personas/${encodeURIComponent(props.personaId)}/avatar/asset?path=${encodeURIComponent(relative)}`
}

function motionCount(): number {
  const groups = info.value?.motions ?? {}
  return Object.values(groups).reduce((sum, list) => sum + list.length, 0)
}
</script>

<template>
  <div class="avatar" data-test="persona-avatar">
    <div class="eyebrow">{{ t('avatar.title') }}</div>

    <p v-if="loading" class="hint">{{ t('common.loading') }}</p>
    <p v-else-if="error" class="hint" role="alert">{{ error }}</p>

    <template v-else-if="info && info.available">
      <div class="avatar__row">
        <img
          v-if="info.preview"
          class="avatar__preview"
          :src="assetUrl(info.preview)"
          :alt="t('avatar.previewAlt', { name: personaId })"
        />
        <div class="avatar__meta">
          <div class="mono">{{ info.model }}</div>
          <div class="hint">
            {{ t('avatar.motions', { n: motionCount() }) }} ·
            {{ t('avatar.expressions', { n: info.expressions?.length ?? 0 }) }} ·
            {{ t('avatar.assets', { n: info.assets ?? 0 }) }}
          </div>
          <!-- The static preview is a deliberate stop, not a bug. -->
          <div class="hint">{{ t('avatar.rendererNone') }}</div>
        </div>
      </div>
    </template>

    <template v-else-if="info">
      <p class="hint">{{ t('avatar.notInstalled') }}</p>
      <p class="hint mono">{{ t('avatar.where', { id: personaId }) }}</p>
      <p v-if="info.hint" class="hint">{{ info.hint }}</p>
    </template>
  </div>
</template>

<style scoped>
.avatar {
  padding: 8px 0;
}
.avatar__row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-top: 6px;
}
.avatar__preview {
  width: 120px;
  height: 120px;
  object-fit: contain;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 6px;
  image-rendering: auto;
}
.avatar__meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
