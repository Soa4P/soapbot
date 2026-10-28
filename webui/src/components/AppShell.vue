<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import { UNAUTHORIZED_EVENT } from '@/api/client'
import LoginDialog from '@/components/LoginDialog.vue'
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
const nav = [
  { to: '/', label: '总览', index: '01' },
  { to: '/runtime', label: '运行状态', index: '02' },
  { to: '/plugins', label: '插件', index: '03' },
  { to: '/security', label: '安全审计', index: '04' },
  { to: '/memory', label: '记忆与知识库', index: '05' },
  { to: '/budget', label: '额度审批', index: '06' },
  { to: '/config', label: '模型与人格', index: '07' },
  { to: '/logs', label: '运行日志', index: '08' },
  { to: '/pipeline', label: '流水线追踪', index: '09' },
  { to: '/metrics', label: '运行指标', index: '10' },
  { to: '/market', label: '插件市场', index: '11' },
]

const title = computed(() => (route.meta.title as string | undefined) ?? '控制台')

const healthPill = computed(() => {
  if (healthError.value) return { cls: 'bad', text: 'API 不可达' }
  if (!health.value) return { cls: '', text: '连接中' }
  return { cls: 'ok', text: 'API 在线' }
})

const authPill = computed(() => {
  switch (auth.mode) {
    case 'token':
      return { cls: 'lamp', text: `TOKEN · ${auth.status?.subject || 'operator'}` }
    case 'loopback':
      return { cls: 'warn', text: '本机直连' }
    case 'invalid':
      return { cls: 'bad', text: '令牌失效' }
    default:
      return { cls: '', text: '未认证' }
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
          <span>{{ item.label }}</span>
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
