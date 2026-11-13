<script setup lang="ts">
import { computed } from 'vue'

import type { ChatMessage } from '@/api/client'
import { t } from '@/i18n'

const props = defineProps<{ message: ChatMessage; pending?: boolean }>()

const mine = computed(() => props.message.role === 'assistant')
const isNote = computed(() => props.message.role === 'note')

/** Delivery state badges: server-archived outcomes, never model-authored. */
const stateBadge = computed(() => {
  if (props.message.state === 'rejected') {
    const reason = props.message.reason ? ` (${props.message.reason})` : ''
    return { cls: 'bubble__tag--rejected', text: t('chat.badge.rejected', { reason }) }
  }
  if (props.message.state === 'send_failed') {
    return { cls: 'bubble__tag--muted', text: t('chat.badge.sendFailed') }
  }
  return null
})

const roleLabel = computed(() => {
  if (isNote.value) return t('chat.role.note')
  if (mine.value) return t('chat.role.assistant')
  return props.message.user_name || t('chat.role.user')
})

const time = computed(() => {
  if (!props.message.created_at) return ''
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(props.message.created_at * 1000))
})

/** Image descriptions are text the operator wrote; links are shown, never fetched. */
const imageHref = computed(() => {
  const desc = props.message.image_desc ?? ''
  return /^https?:\/\//.test(desc) ? desc : ''
})
</script>

<template>
  <article
    class="bubble"
    :class="{ 'bubble--mine': mine, 'bubble--note': isNote, 'bubble--pending': pending }"
  >
    <header class="bubble__head">
      <span class="bubble__who">{{ roleLabel }}</span>
      <span v-if="isNote" class="bubble__tag">{{ t('chat.badge.note') }}</span>
      <span v-if="pending" class="bubble__tag bubble__tag--muted">{{ t('chat.badge.notSent') }}</span>
      <span v-if="stateBadge" class="bubble__tag" :class="stateBadge.cls">{{ stateBadge.text }}</span>
      <time v-if="time" class="bubble__time">{{ time }}</time>
    </header>

    <p class="bubble__body">{{ message.content }}</p>

    <p v-if="message.image_desc" class="bubble__image">
      <span class="bubble__tag bubble__tag--muted">{{ t('chat.badge.image') }}</span>
      <a v-if="imageHref" :href="imageHref" target="_blank" rel="noopener noreferrer">
        {{ imageHref }}
      </a>
      <span v-else>{{ message.image_desc }}</span>
    </p>
  </article>
</template>

<style scoped>
.bubble {
  max-width: min(68ch, 82%);
  padding: 10px 12px 9px;
  border: 1px solid var(--border);
  border-radius: 12px 12px 12px 4px;
  background: var(--surface);
  box-shadow: 0 1px 1px rgba(15, 23, 42, 0.03);
}

.bubble--mine {
  margin-left: auto;
  border-color: var(--brand-line);
  border-radius: 12px 12px 4px 12px;
  background: linear-gradient(180deg, var(--brand-soft), var(--surface));
}

.bubble--note {
  margin-left: auto;
  border-style: dashed;
  border-color: var(--warn-line);
  background: var(--warn-soft);
  border-radius: 12px;
}

.bubble--pending {
  opacity: 0.75;
}

.bubble__head {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 3px;
  font-size: 11px;
  color: var(--ink-3);
}

.bubble__who {
  font-weight: 600;
  color: var(--ink-2);
}

.bubble__tag {
  padding: 0 5px;
  border: 1px solid var(--warn-line);
  border-radius: 999px;
  background: var(--surface);
  font-size: 10px;
  line-height: 15px;
  color: var(--warn);
}

.bubble__tag--muted {
  border-color: var(--idle-line);
  color: var(--ink-3);
}

.bubble__tag--rejected {
  border-color: var(--danger-line, #e11d4844);
  background: var(--danger-soft, #fef2f2);
  color: var(--danger, #be123c);
}

.bubble__time {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.bubble__body {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: var(--ink);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.bubble__image {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--ink-3);
}

.bubble__image a {
  color: var(--brand);
  text-decoration: underline;
  text-underline-offset: 2px;
  overflow-wrap: anywhere;
}
</style>
