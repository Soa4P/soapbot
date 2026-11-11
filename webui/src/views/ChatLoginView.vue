<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, chatApi } from '@/api/client'
import { t } from '@/i18n'

const router = useRouter()
const route = useRoute()

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const invite = ref('')
const showPassword = ref(false)
const busy = ref(false)
const error = ref('')

const canSubmit = computed(() => {
  if (busy.value) return false
  if (username.value.trim().length < 3 || password.value.length < 8) return false
  return mode.value === 'login' || invite.value.trim().length >= 8
})

function switchMode(next: 'login' | 'register'): void {
  mode.value = next
  error.value = ''
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  busy.value = true
  error.value = ''
  try {
    if (mode.value === 'login') {
      await chatApi.login(username.value.trim(), password.value)
    } else {
      await chatApi.register(invite.value.trim(), username.value.trim(), password.value)
    }
    const next = typeof route.query.next === 'string' ? route.query.next : '/chat'
    await router.replace(next)
  } catch (err) {
    const message = err instanceof ApiError ? err.message : (err as Error).message
    error.value = message || t('chat.messages.error')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login__card">
      <header class="login__head">
        <p class="login__mark">SOAPBOT · ARCHIVE</p>
        <h1>{{ t('chat.login.title') }}</h1>
        <p class="login__sub">{{ t('chat.login.subtitle') }}</p>
      </header>

      <div class="login__modes" role="tablist" :aria-label="t('chat.login.title')">
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'login'"
          :class="{ 'is-active': mode === 'login' }"
          @click="switchMode('login')"
        >
          {{ t('chat.login.submit') }}
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'register'"
          :class="{ 'is-active': mode === 'register' }"
          @click="switchMode('register')"
        >
          {{ t('chat.login.toRegister') }}
        </button>
      </div>

      <form class="login__form" @submit.prevent="submit">
        <label class="field">
          <span>{{ t('chat.login.username') }}</span>
          <input
            v-model="username"
            name="username"
            autocomplete="username"
            inputmode="text"
            required
            minlength="3"
            maxlength="32"
          />
        </label>

        <label v-if="mode === 'register'" class="field">
          <span>{{ t('chat.login.invite') }}</span>
          <input v-model="invite" name="invite" autocomplete="off" required />
        </label>

        <label class="field">
          <span>{{ t('chat.login.password') }}</span>
          <span class="field__password">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              name="password"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              required
              minlength="8"
              maxlength="128"
            />
            <button
              type="button"
              class="field__toggle"
              :aria-label="showPassword ? t('chat.login.hidePassword') : t('chat.login.showPassword')"
              @click="showPassword = !showPassword"
            >
              {{ showPassword ? '◉' : '◎' }}
            </button>
          </span>
        </label>

        <p class="login__hint">
          {{ mode === 'login' ? t('chat.login.hint') : t('chat.login.registerHint') }}
        </p>

        <p v-if="error" class="login__error" role="alert">{{ error }}</p>

        <button class="login__submit" type="submit" :disabled="!canSubmit">
          {{ busy ? t('chat.composer.saving') : mode === 'login' ? t('chat.login.submit') : t('chat.login.register') }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(1200px 520px at 15% -10%, var(--brand-soft), transparent 60%),
    radial-gradient(900px 420px at 110% 110%, var(--ok-soft), transparent 55%),
    var(--bg);
}

.login__card {
  width: min(420px, 100%);
  padding: 26px 24px 24px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.login__mark {
  margin: 0 0 8px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  color: var(--brand);
}

.login__head h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--ink);
}

.login__sub {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-3);
}

.login__modes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin: 18px 0 16px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-3);
}

.login__modes button {
  height: 30px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--ink-3);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.login__modes button.is-active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.login__form {
  display: grid;
  gap: 12px;
}

.field {
  display: grid;
  gap: 5px;
  font-size: 12px;
  color: var(--ink-2);
}

.field input {
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2);
  color: var(--ink);
  font: inherit;
  font-size: 13px;
}

.field input:focus-visible {
  border-color: var(--brand);
  outline: none;
  box-shadow: 0 0 0 3px var(--brand-soft);
}

.field__password {
  position: relative;
  display: block;
}

.field__password input {
  width: 100%;
  padding-right: 36px;
}

.field__toggle {
  position: absolute;
  top: 0;
  right: 0;
  width: 36px;
  height: 36px;
  border: 0;
  background: transparent;
  color: var(--ink-3);
  font-size: 14px;
  cursor: pointer;
}

.login__hint {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--ink-3);
}

.login__error {
  margin: 0;
  padding: 7px 9px;
  border: 1px solid var(--danger-line);
  border-radius: 7px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12px;
  line-height: 1.45;
}

.login__submit {
  height: 38px;
  border: 1px solid var(--brand);
  border-radius: 9px;
  background: linear-gradient(180deg, var(--brand), var(--brand-dark));
  color: var(--on-brand);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: filter 120ms ease, transform 120ms ease;
}

.login__submit:hover:not(:disabled) {
  filter: brightness(1.06);
}

.login__submit:active:not(:disabled) {
  transform: translateY(1px);
}

.login__submit:disabled {
  border-color: var(--border-strong);
  background: var(--surface-3);
  color: var(--ink-3);
  cursor: not-allowed;
}

.login__submit:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .login__submit {
    transition: none;
  }
}
</style>
