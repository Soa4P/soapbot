<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import { UNAUTHORIZED_EVENT } from '@/api/client'
import LoginDialog from '@/components/LoginDialog.vue'
import { t } from '@/i18n'
import { bumpRefresh } from '@/lib/refresh'
import { uptime as fmtUptime } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()

const health = ref<{ status: string; version: string; uptime_seconds: number } | null>(null)
const healthError = ref('')
let timer: number | undefined

/**
 * The numbers are stable identifiers, not sort order. An operator on a support call
 * says "the 04 page" and it means something; 07 and 08 were appended rather than
 * inserted for the same reason. Never renumber — add 09, 10, 11.
 */
/**
 * Labels are i18n keys, not literals, so switching language re-renders the rail.
 * The index stays a fixed string: it is an identifier ("the 04 page"), and would stop
 * being one if it were renumbered per locale.
 */
const nav = [
  { to: '/', key: 'nav.01', index: '01' },
  { to: '/runtime', key: 'nav.02', index: '02' },
  { to: '/plugins', key: 'nav.03', index: '03' },
  { to: '/security', key: 'nav.04', index: '04' },
  { to: '/memory', key: 'nav.05', index: '05' },
  { to: '/budget', key: 'nav.06', index: '06' },
  { to: '/config', key: 'nav.07', index: '07' },
  { to: '/logs', key: 'nav.08', index: '08' },
  { to: '/pipeline', key: 'nav.09', index: '09' },
  { to: '/metrics', key: 'nav.10', index: '10' },
  { to: '/market', key: 'nav.11', index: '11' },
  { to: '/settings', key: 'nav.12', index: '12' },
]

/**
 * Page title comes from the route's own key when it has one, so the heading and the
 * rail can never disagree. Routes keep a Chinese `title` in `meta` for the document
 * title fallback (browser tab before the catalogue loads).
 */
const title = computed(() => {
  const key = route.meta.titleKey as string | undefined
  if (key) return t(key)
  return (route.meta.title as string | undefined) ?? t('app.console')
})

const healthPill = computed(() => {
  if (healthError.value) return { cls: 'bad', text: t('app.health.unreachable') }
  if (!health.value) return { cls: '', text: t('app.health.connecting') }
  return { cls: 'ok', text: t('app.health.online') }
})

const authPill = computed(() => {
  switch (auth.mode) {
    case 'token':
      return { cls: 'lamp', text: `${t('app.auth.token')} · ${auth.status?.subject || 'operator'}` }
    case 'loopback':
      return { cls: 'warn', text: t('app.auth.loopback') }
    case 'invalid':
      return { cls: 'bad', text: t('app.auth.invalid') }
    default:
      return { cls: '', text: t('app.auth.none') }
  }
})

async function loadHealth(): Promise<void> {
  try {
    const response = await fetch('/api/health')
    if (!response.ok) throw new Error(String(response.status))
    health.value = await response.json()
    healthError.value = ''
  } catch (err) {
    healthError.value = (err as Error).message
  }
}

function onUnauthorized(): void {
  void auth.refresh().then(() => {
    if (!auth.authenticated) auth.openDialog()
  })
}

onMounted(() => {
  void loadHealth()
  void auth.refresh()
  timer = window.setInterval(() => void loadHealth(), 20_000)
  window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
  window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
})
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>

  <div class="shell">
    <aside class="rail">
      <div class="rail__brand">
        <strong>SOAPBOT</strong>
        <span>control surface</span>
      </div>

      <nav class="rail__nav" aria-label="主导航">
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="rail__link">
          <span class="idx" aria-hidden="true">{{ item.index }}</span>
          <span>{{ t(item.key) }}</span>
        </RouterLink>
      </nav>

      <div class="rail__foot">
        <span>v{{ health?.version ?? '—' }}</span>
        <span>{{ health ? fmtUptime(health.uptime_seconds) : '—' }}</span>
        <span>{{ auth.status?.loopback ? 'loopback' : 'remote' }}</span>
      </div>
    </aside>

    <main id="main-content" class="main" tabindex="-1">
      <header class="strip">
        <span class="strip__title">{{ title }}</span>
        <span class="pill" :class="healthPill.cls"><i class="dot" />{{ healthPill.text }}</span>
        <span class="pill" :class="authPill.cls"><i class="dot" />{{ authPill.text }}</span>

        <span class="strip__spacer" />

        <button class="btn ghost" type="button" @click="bumpRefresh()">刷新</button>
        <button
          v-if="auth.hasToken"
          class="btn ghost"
          type="button"
          @click="auth.logout()"
        >
          退出
        </button>
        <button v-else class="btn lamp" type="button" @click="auth.openDialog()">
          {{ auth.mode === 'loopback' ? '获取令牌' : '登录' }}
        </button>
      </header>

      <div class="page">
        <div v-if="healthError" class="error-banner" role="alert">
          无法访问 API：{{ healthError }}。服务可能未启动，或端口被占用。
        </div>
        <div v-else-if="!auth.authenticated" class="warn-banner" role="status">
          当前会话未认证。远程访问必须先在右上角登录，否则所有管理接口都会返回 401。
        </div>

        <RouterView />
      </div>
    </main>

    <LoginDialog />
  </div>
</template>
