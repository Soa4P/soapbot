<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { t } from '@/i18n'

/**
 * "What is this page for, and when should I come here."
 *
 * The panel had twelve pages of dense tables and not one sentence saying why a person
 * would open them. That is the difference between a control panel and a wall of JSON:
 * the numbers were right and the page still answered nothing.
 *
 * Rendered once from the route's `index` rather than copied into twelve views, so a new
 * page cannot ship without somebody deciding what it is for. The strings are literal
 * `t('intro.NN.purpose')` calls on purpose — `check-i18n.mjs` can only verify keys it
 * can see, and a template built from the index would be invisible to it.
 */
const route = useRoute()

const index = computed(() => String(route.meta.index ?? ''))

const text = computed(() => {
  switch (index.value) {
    case '01':
      return { purpose: t('intro.01.purpose'), when: t('intro.01.when') }
    case '02':
      return { purpose: t('intro.02.purpose'), when: t('intro.02.when') }
    case '03':
      return { purpose: t('intro.03.purpose'), when: t('intro.03.when') }
    case '04':
      return { purpose: t('intro.04.purpose'), when: t('intro.04.when') }
    case '05':
      return { purpose: t('intro.05.purpose'), when: t('intro.05.when') }
    case '06':
      return { purpose: t('intro.06.purpose'), when: t('intro.06.when') }
    case '07':
      return { purpose: t('intro.07.purpose'), when: t('intro.07.when') }
    case '08':
      return { purpose: t('intro.08.purpose'), when: t('intro.08.when') }
    case '09':
      return { purpose: t('intro.09.purpose'), when: t('intro.09.when') }
    case '10':
      return { purpose: t('intro.10.purpose'), when: t('intro.10.when') }
    case '11':
      return { purpose: t('intro.11.purpose'), when: t('intro.11.when') }
    case '12':
      return { purpose: t('intro.12.purpose'), when: t('intro.12.when') }
    default:
      return null
  }
})
</script>

<template>
  <div v-if="text" class="intro">
    <p class="intro__purpose">{{ text.purpose }}</p>
    <details class="intro__when">
      <summary>{{ t('intro.summary') }}</summary>
      <p class="intro__when-body">{{ text.when }}</p>
    </details>
  </div>
</template>

<style scoped>
.intro {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px 16px;
  padding: 10px 14px;
  margin: 0 0 14px;
  border-left: 3px solid var(--border-strong);
  background: var(--surface-3);
  border-radius: 0 8px 8px 0;
}
.intro__purpose {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--ink);
}
.intro__when summary {
  font-size: 13px;
  color: var(--ink-3);
  cursor: pointer;
}
.intro__when-body {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--ink-2);
  max-width: 72ch;
}
</style>
