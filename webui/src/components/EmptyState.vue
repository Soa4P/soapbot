<script setup lang="ts">
import { RouterLink } from 'vue-router'

/**
 * "Nothing here yet" plus the one thing to do about it.
 *
 * Every empty state in the panel used to be a single grey line of monospace — "还没有需要
 * 你处理的事件。" — which is accurate and leaves the reader exactly where they were. An
 * empty table is not a dead end; it is usually a page that has not been configured yet,
 * and the fix lives two clicks away.
 *
 * So this takes a lead sentence (what is true now) and, optionally, a next step. The
 * link is a real `RouterLink`, not a click handler on a div, so it is focusable and
 * middle-clickable for free.
 */
withDefaults(
  defineProps<{
    /** What is true right now. One sentence, no jargon. */
    lead: string
    /** Why it is empty, or what would make it non-empty. Optional. */
    hint?: string
    /** Where to go to fix it. Omitted when there is nothing to do. */
    to?: string
    /** Label for that link. Required in practice when `to` is set. */
    action?: string
  }>(),
  { hint: '', to: '', action: '' },
)
</script>

<template>
  <div class="empty-state">
    <p class="empty-state__lead">{{ lead }}</p>
    <p v-if="hint" class="empty-state__hint">{{ hint }}</p>
    <RouterLink v-if="to && action" :to="to" class="btn ghost empty-state__action">
      {{ action }}
    </RouterLink>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 26px 18px;
  text-align: center;
}
.empty-state__lead {
  margin: 0;
  font-size: 13px;
  color: var(--ink-2);
}
.empty-state__hint {
  margin: 0;
  max-width: 52ch;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--ink-3);
}
.empty-state__action {
  margin-top: 6px;
  text-decoration: none;
}
</style>
