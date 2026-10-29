<script setup lang="ts">
import { computed, ref } from 'vue'

import { t } from '@/i18n'
import { useFocusTrap } from '@/lib/useFocusTrap'

/**
 * Confirmation for an action that changes state.
 *
 * The `tone` prop exists because "delete this plugin" and "revoke approval" need
 * different words. A single generic "Are you sure?" trains people to click through
 * it; naming what is lost — and whether it can be undone — is the only thing that
 * makes a confirmation dialog worth the interruption.
 */
const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    /** Consequence in plain language. Say what is destroyed, not "this action". */
    detail: string
    confirmLabel?: string
    cancelLabel?: string
    tone?: 'default' | 'danger'
    /** True when the action cannot be undone; rendered as a separate warning line. */
    irreversible?: boolean
    busy?: boolean
  }>(),
  {
    confirmLabel: '',
    cancelLabel: '',
    tone: 'default',
    irreversible: false,
    busy: false,
  },
)

const emit = defineEmits<{ confirm: []; cancel: [] }>()

// Empty default, resolved at render time. A literal default is evaluated once when the
// component definition is created, so it would keep the language the module happened to
// load in — the same trap as a module-level label array.
const cancelText = computed(() => props.cancelLabel || t('common.cancel'))
const confirmText = computed(() => props.confirmLabel || t('common.confirm'))

const panel = ref<HTMLElement | null>(null)
const confirmBtn = ref<HTMLElement | null>(null)
const isOpen = ref(false)

// `open` is mirrored into a local ref so the trap can watch one reactive source and
// so that Esc can be refused without mutating a prop.
isOpen.value = props.open

useFocusTrap(panel, isOpen, {
  // Cancel is the default target: pressing Enter on a destructive dialog should not
  // be the fastest path to deleting something.
  onEscape: () => emit('cancel'),
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="overlay" @click.self="emit('cancel')">
      <div
        ref="panel"
        class="dialog"
        role="alertdialog"
        aria-modal="true"
        :aria-labelledby="'cf-title'"
        :aria-describedby="'cf-detail'"
      >
        <div class="dialog__head">
          <h2 id="cf-title">{{ title }}</h2>
        </div>
        <div class="dialog__body">
          <p id="cf-detail" style="margin: 0">{{ detail }}</p>
          <p v-if="irreversible" class="warn-banner" style="margin: 0">
            {{ t('common.irreversible') }}
          </p>
        </div>
        <div class="dialog__foot">
          <button ref="confirmBtn" class="btn ghost" type="button" :disabled="busy" @click="emit('cancel')">
            {{ cancelText }}
          </button>
          <button
            class="btn"
            :class="tone === 'danger' ? 'danger' : 'lamp'"
            type="button"
            :disabled="busy"
            @click="emit('confirm')"
          >
            {{ busy ? t('common.working') : confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
