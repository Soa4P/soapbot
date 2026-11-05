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

const copied = ref('')

async function copy(value: string, which: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value)
    copied.value = which
    window.setTimeout(() => {
      copied.value = ''
    }, 2000)
  } catch {
    /* clipboard needs a secure context; the value stays on screen to select manually */
  }
}

/** The server resolves the real path (systemd, Docker and custom DATA_DIR all differ), so
 * the operator never has to guess where the file went. Show the command too: on a remote
 * host the fastest route is `soapbot token`, not hunting through directories. */
const tokenCommand = 'soapbot token'
const resetCommand = 'soapbot token --reset'
const spent = computed(() => auth.status?.bootstrap_state === 'redeemed')
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

        <!-- The point of this card: nobody should have to know where the file lives. The
             server sends its real absolute path, and the command works on a remote host
             where there is no file explorer at all. -->
        <div class="login__where" role="group" :aria-label="t('login.whereTitle')">
          <div class="eyebrow">{{ t('login.whereTitle') }}</div>
          <p class="muted" style="margin: 4px 0 8px">{{ t('login.whereHint') }}</p>

          <div v-if="spent" class="login__cmd">
            <code>{{ resetCommand }}</code>
            <button class="btn ghost" type="button" @click="copy(resetCommand, 'reset')">
              {{ copied === 'reset' ? t('login.copied') : t('login.copy') }}
            </button>
          </div>
          <p v-if="spent" class="muted" style="margin: 4px 0 8px">{{ t('login.resetHint') }}</p>

          <template v-else>
            <div v-if="auth.status?.bootstrap_path" class="login__cmd">
              <code>{{ auth.status.bootstrap_path }}</code>
              <button
                class="btn ghost"
                type="button"
                @click="copy(auth.status.bootstrap_path, 'path')"
              >
                {{ copied === 'path' ? t('login.copied') : t('login.copy') }}
              </button>
            </div>
            <div class="login__cmd">
              <code>{{ tokenCommand }}</code>
              <button class="btn ghost" type="button" @click="copy(tokenCommand, 'cmd')">
                {{ copied === 'cmd' ? t('login.copied') : t('login.copy') }}
              </button>
            </div>
          </template>
        </div>

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

<style scoped>
.login__where {
  border: 1px solid var(--border);
  border-radius: var(--radius, 8px);
  padding: 10px 12px;
  margin: 0 0 14px;
  background: var(--surface-2, transparent);
}
.login__cmd {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
  flex-wrap: wrap;
}
.login__cmd code {
  font-family: var(--mono);
  word-break: break-all;
}
</style>
