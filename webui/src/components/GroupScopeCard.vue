<script setup lang="ts">
import { ref, watch } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
import { useAsync } from '@/lib/useAsync'

/**
 * "Where does it speak" and "where does it learn" are two different questions.
 *
 * They used to be one list, and the archive step sat behind the wake check, so a group
 * message nobody @-ed was never stored: the bot only remembered what it was asked
 * about. Both halves are configurable now, and this card is the only place an operator
 * can set them without editing `.env` by hand.
 *
 * Both lists read the same way: empty means "everywhere". They are independent, so an
 * operator can collect in a busy group while staying quiet there, or reply somewhere
 * without keeping a record of it.
 */
const scope = useAsync(() => api.groupScope())

const draftReply = ref('')
const draftCollect = ref('')
const saving = ref(false)
const saved = ref(false)
const error = ref('')

watch(
  () => scope.data.value,
  (value) => {
    if (!value) return
    draftReply.value = (value.reply_groups ?? []).join(', ')
    draftCollect.value = (value.memory_collect_groups ?? []).join(', ')
  },
  { immediate: true },
)

/** Accept `111, 222`, `111 222` and full-width commas — people paste from a chat. */
function splitIds(raw: string): string[] {
  return raw
    .split(/[\s,，、;；]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

const replyIds = () => splitIds(draftReply.value)
const collectIds = () => splitIds(draftCollect.value)

const replySummary = () =>
  replyIds().length ? t('scope.replyListed', { count: replyIds().length }) : t('scope.all')

const collectSummary = () =>
  collectIds().length ? t('scope.collectListed', { count: collectIds().length }) : t('scope.all')

async function save(): Promise<void> {
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    const result = await api.writeGroupScope({
      reply_groups: replyIds(),
      memory_collect_groups: collectIds(),
    })
    draftReply.value = result.reply_groups.join(', ')
    draftCollect.value = result.memory_collect_groups.join(', ')
    saved.value = true
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
      <h2 class="panel__title">{{ t('scope.title') }}</h2>
      <p class="muted" style="margin: 4px 0 0">{{ t('scope.detail') }}</p>
    </header>

    <div class="scope">
      <label class="scope__field">
        <span class="eyebrow">{{ t('scope.replyLabel') }}</span>
        <input
          v-model="draftReply"
          class="field"
          type="text"
          inputmode="numeric"
          autocomplete="off"
          spellcheck="false"
          :placeholder="t('scope.placeholder')"
        />
        <span class="hint">{{ t('scope.replyHint') }}</span>
        <span class="hint scope__now">{{ replySummary() }}</span>
      </label>

      <label class="scope__field">
        <span class="eyebrow">{{ t('scope.collectLabel') }}</span>
        <input
          v-model="draftCollect"
          class="field"
          type="text"
          inputmode="numeric"
          autocomplete="off"
          spellcheck="false"
          :placeholder="t('scope.placeholder')"
        />
        <span class="hint">{{ t('scope.collectHint') }}</span>
        <span class="hint scope__now">{{ collectSummary() }}</span>
      </label>
    </div>

    <p class="hint" style="margin: 8px 0 0">{{ t('scope.restart') }}</p>
    <p v-if="scope.data.value?.legacy_alias_in_use" class="hint" style="margin: 4px 0 0">
      {{ t('scope.legacy') }}
    </p>

    <div class="row" style="margin-top: 10px">
      <button class="btn lamp" type="button" :disabled="saving" @click="save">
        {{ saving ? t('scope.saving') : t('scope.save') }}
      </button>
      <span v-if="saved" class="hint" style="margin: 0; color: var(--ok)">{{ t('scope.saved') }}</span>
      <span v-if="error" class="hint" style="margin: 0; color: var(--danger)">{{ error }}</span>
    </div>
  </section>
</template>

<style scoped>
.scope {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
  margin-top: 12px;
}
.scope__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.scope__now {
  font-size: 12px;
}
</style>
