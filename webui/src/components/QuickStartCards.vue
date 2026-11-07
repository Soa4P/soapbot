<script setup lang="ts">
import { computed } from 'vue'

import { api } from '@/api/client'
import { t } from '@/i18n'
import { useAsync } from '@/lib/useAsync'

/**
 * The two things a first-time operator has to do, on the page they land on.
 *
 * Both entry points existed and both were buried: "接入 AI" lived on page 07 behind a
 * provider table, and "登录 QQ" lived inside the protocol-end card on the same page, below
 * the fold. Someone who had just installed this saw a dashboard of zeros and had no way to
 * learn that the zeros were caused by two missing steps rather than by a broken bot.
 *
 * `SetupGuide` already answers "what is still missing" as a five-row checklist. This is a
 * different question — "what do I do first, and where" — and it is deliberately only two
 * cards, because a first-run page that lists five tasks is a page people close. The
 * checklist stays for the detailed state; this strip is the doorway.
 *
 * It disappears entirely once both are done. A permanent "you have configured things"
 * banner is the kind of thing that trains people to stop reading the top of the page.
 *
 * No new endpoint: the runtime payload already carries the adapter map with an `online`
 * flag, and the providers payload already carries the list. A dedicated onboarding endpoint
 * would be a second implementation of "is it configured", and the two would drift.
 */
const runtime = useAsync(() => api.runtime(), 'overview.runtime')
const providers = useAsync(() => api.providers(), 'overview.providers')

const providerCount = computed(() => (providers.data.value?.providers ?? []).length)

const adapters = computed<any[]>(() => {
  const map = runtime.data.value?.adapters ?? {}
  return Object.values(map) as any[]
})

/**
 * "Online" is the adapter's own report, not a ping from here.
 *
 * A panel that probes the protocol end itself would disagree with the runtime that is
 * actually holding the connection — and the runtime is the one that knows, because it is
 * the process that would receive the message.
 */
const online = computed(() => adapters.value.filter((adapter) => adapter.online).length)
const configured = computed(() => adapters.value.length > 0)

const aiDone = computed(() => providerCount.value > 0)
const qqDone = computed(() => configured.value && online.value > 0)

/** Hidden when both are done, or while the first load is still in flight. */
const visible = computed(() => {
  if (runtime.loading.value && !runtime.data.value) return false
  if (providers.loading.value && !providers.data.value) return false
  return !(aiDone.value && qqDone.value)
})
</script>

<template>
  <div v-if="visible" class="quickstart">
    <!-- Left: the model. Without a provider every reply fails, and the failure is a 500 in
         a log rather than a message in the group — so this is the one that must be first. -->
    <section class="quickstart__card">
      <div class="quickstart__head">
        <h3>{{ t('quickstart.aiTitle') }}</h3>
        <span class="pill" :class="aiDone ? 'ok' : 'bad'">
          <i class="dot" />{{ aiDone ? t('quickstart.done') : t('quickstart.todo') }}
        </span>
      </div>
      <p class="hint quickstart__text">
        {{ aiDone ? t('quickstart.aiDone', { n: providerCount }) : t('quickstart.aiMissing') }}
      </p>
      <div class="quickstart__foot">
        <RouterLink v-if="!aiDone" class="btn" to="/config">{{ t('quickstart.aiGo') }}</RouterLink>
        <RouterLink v-else class="quickstart__link" to="/config">{{ t('quickstart.aiManage') }}</RouterLink>
      </div>
    </section>

    <!-- Right: the account. A provider with no logged-in account answers nobody. -->
    <section class="quickstart__card">
      <div class="quickstart__head">
        <h3>{{ t('quickstart.qqTitle') }}</h3>
        <span class="pill" :class="qqDone ? 'ok' : 'bad'">
          <i class="dot" />{{ qqDone ? t('quickstart.online', { n: online }) : t('quickstart.offline') }}
        </span>
      </div>
      <p class="hint quickstart__text">
        {{ qqDone ? t('quickstart.qqDone', { n: online }) : t('quickstart.qqMissing') }}
      </p>
      <div class="quickstart__foot">
        <RouterLink v-if="!qqDone" class="btn" to="/config">{{ t('quickstart.qqGo') }}</RouterLink>
        <RouterLink v-else class="quickstart__link" to="/config">{{ t('quickstart.qqManage') }}</RouterLink>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* Two equal columns, same height, hairline border, no illustration. The panel's whole
   visual language is "quiet surface, status colour only for status", and a first-run
   banner is exactly where that discipline is easiest to break. */
.quickstart {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

@media (max-width: 860px) {
  .quickstart {
    grid-template-columns: minmax(0, 1fr);
  }
}

.quickstart__card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.quickstart__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.quickstart__head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
}

.quickstart__text {
  margin: 0;
  flex: 1;
}

.quickstart__foot {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Once done, the primary button would be a lie: there is nothing left to do, only
   something to review. A text link says that without competing for attention. */
.quickstart__link {
  font-size: 13px;
  color: var(--ink-3);
  text-decoration: none;
}

.quickstart__link:hover,
.quickstart__link:focus-visible {
  color: var(--brand);
  text-decoration: underline;
}
</style>
