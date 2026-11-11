<script setup lang="ts">
import { computed, ref } from 'vue'

import { t } from '@/i18n'

const props = defineProps<{ disabled?: boolean; saving?: boolean }>()
const emit = defineEmits<{ submit: [text: string] }>()

const text = ref('')
const canSubmit = computed(() => text.value.trim().length > 0 && !props.disabled && !props.saving)

function send(): void {
  if (!canSubmit.value) return
  emit('submit', text.value.trim())
  text.value = ''
}
</script>

<template>
  <form class="composer" @submit.prevent="send">
    <p class="composer__notice">
      <span aria-hidden="true">◦</span>
      {{ t('chat.composer.notice') }}
    </p>

    <label class="composer__label" for="chat-note">{{ t('chat.composer.label') }}</label>
    <div class="composer__row">
      <textarea
        id="chat-note"
        v-model="text"
        class="composer__input"
        rows="2"
        maxlength="4000"
        :placeholder="t('chat.composer.placeholder')"
        :disabled="disabled"
        @keydown.ctrl.enter.prevent="send"
        @keydown.meta.enter.prevent="send"
      />
      <button class="composer__send" type="submit" :disabled="!canSubmit">
        {{ saving ? t('chat.composer.saving') : t('chat.composer.save') }}
      </button>
    </div>
  </form>
</template>

<style scoped>
.composer {
  padding: 10px 14px 12px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}

.composer__notice {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 7px;
  font-size: 11px;
  color: var(--warn);
}

.composer__label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.composer__row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.composer__input {
  flex: 1;
  min-height: 44px;
  max-height: 132px;
  padding: 9px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-2);
  color: var(--ink);
  font: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  transition: border-color 120ms ease, box-shadow 120ms ease;
}

.composer__input:focus-visible {
  border-color: var(--brand);
  outline: none;
  box-shadow: 0 0 0 3px var(--brand-soft);
}

.composer__send {
  height: 38px;
  padding: 0 14px;
  border: 1px solid var(--brand);
  border-radius: var(--radius);
  background: var(--brand);
  color: var(--on-brand);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 120ms ease, transform 120ms ease;
}

.composer__send:hover:not(:disabled) {
  background: var(--brand-dark);
}

.composer__send:active:not(:disabled) {
  transform: translateY(1px);
}

.composer__send:disabled {
  border-color: var(--border-strong);
  background: var(--surface-3);
  color: var(--ink-3);
  cursor: not-allowed;
}

.composer__send:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .composer__input,
  .composer__send {
    transition: none;
  }
}
</style>
