<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
import { useAsync } from '@/lib/useAsync'

/**
 * Which card speaks in which group.
 *
 * ``PersonaStore.bind_group`` existed but nothing loaded or saved it, so a binding made
 * at runtime disappeared on the next restart and the panel had no way to set one. This
 * writes `SOAPBOT_GROUP_PERSONAS` through the same `.env` path as the access lists.
 *
 * The effective binding is shown as read-only text: it is what the *running* process
 * resolved, which can differ from the file until a restart.
 */
const personas = useAsync(() => api.personas(), 'config.personas')

const draft = ref('')
const saving = ref(false)
const saved = ref(false)
const error = ref('')

const current = computed<Record<string, string>>(
  () => (personas.data.value?.binding?.groups ?? {}) as Record<string, string>,
)

const currentText = computed(() => {
  const entries = Object.entries(current.value)
  if (!entries.length) return t('persona.bind.none')
  return entries.map(([group, id]) => `${group} → ${id}`).join('，')
})

watch(
  () => current.value,
  (groups) => {
    if (draft.value) return // do not overwrite an unsaved edit
    draft.value = Object.entries(groups)
      .map(([group, id]) => `${group}:${id}`)
      .join(', ')
  },
  { immediate: true },
)

async function save(): Promise<void> {
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    await api.writePersonaBinding({ group_personas: draft.value.trim() })
    saved.value = true
    await personas.reload()
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="panel">
    <header class="panel__head">
      <h2>{{ t('persona.bind.title') }}</h2>
      <p class="muted" style="margin: 4px 0 0">{{ t('persona.bind.detail') }}</p>
    </header>

    <div class="stack" style="margin-top: 12px">
      <label class="eyebrow" for="persona-bind">{{ t('persona.bind.label') }}</label>
      <input
        id="persona-bind"
        v-model="draft"
        class="field"
        type="text"
        autocomplete="off"
        spellcheck="false"
        :placeholder="t('persona.bind.placeholder')"
      />
      <p class="hint" style="margin: 0">{{ t('persona.bind.hint') }}</p>
      <p class="hint" style="margin: 0">{{ t('persona.bind.current', { detail: currentText }) }}</p>
    </div>

    <div class="row" style="margin-top: 10px">
      <button class="btn lamp" type="button" :disabled="saving" @click="save">
        {{ saving ? t('persona.bind.saving') : t('persona.bind.save') }}
      </button>
      <span v-if="saved" class="hint" style="margin: 0; color: var(--ok)">
        {{ t('persona.bind.saved') }}
      </span>
      <span v-if="error" class="hint" style="margin: 0; color: var(--danger)">{{ error }}</span>
    </div>
  </section>
</template>
