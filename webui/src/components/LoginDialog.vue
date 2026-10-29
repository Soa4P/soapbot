<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { t } from '@/i18n'

import { useFocusTrap } from '@/lib/useFocusTrap'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const token = ref('')
const panel = ref<HTMLElement | null>(null)
const tokenInput = ref<HTMLInputElement | null>(null)

// A computed mirror rather than a plain copy: the trap needs one reactive source to
// watch, and the store's flag is the real one. Copying it into a local ref would
// leave two open/closed states that can disagree.
const isOpen = computed(() => auth.dialogOpen)

useFocusTrap(panel, isOpen, {
  onEscape: () => auth.closeDialog(),
  // The token field, not the first focusable element: this dialog has exactly one
  // thing to do, and making the operator Tab into it is pure friction.
  initialFocus: tokenInput,
})

watch(
  () => auth.dialogOpen,
  (open) => {
    if (open) token.value = ''
  },
)

async function submit(): Promise<void> {
  if (!token.value.trim() || auth.busy) return
  await auth.login(token.value)
}
</script>

<template>
  <div v-if="auth.dialogOpen" class="overlay" @click.self="auth.closeDialog()">
    <div
      ref="panel"
      class="dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="login-title"
      aria-describedby="login-detail"
    >
      <div class="dialog__head">
        <div class="eyebrow">bootstrap</div>
        <h2 id="login-title">{{ t('login.title') }}</h2>
      </div>

      <div class="dialog__body">
        <p id="login-detail" class="muted" style="margin: 0">
          {{ t('login.detail') }}
        </p>

        <form class="stack" @submit.prevent="submit">
          <label class="eyebrow" for="login-token">{{ t('login.label') }}</label>
          <input
            id="login-token"
            ref="tokenInput"
            v-model="token"
            class="field"
            type="password"
            autocomplete="off"
            spellcheck="false"
            placeholder="init token"
          />
          <div class="row">
            <button class="btn lamp" type="submit" :disabled="!token.trim() || auth.busy">
              {{ auth.busy ? t('login.checking') : t('shell.login') }}
            </button>
            <button class="btn ghost" type="button" @click="auth.closeDialog()">{{ t('common.cancel') }}</button>
          </div>
        </form>

        <div v-if="auth.error" class="error-banner" role="alert">{{ auth.error }}</div>

        <p v-if="!auth.canLogin" class="warn-banner" style="margin: 0">
          {{ t('login.spent') }}
        </p>
      </div>
    </div>
  </div>
</template>
