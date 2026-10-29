import { watch } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import { locale, t } from '@/i18n'

/**
 * Eight pages, lazy-loaded.
 *
 * The index numbers are shown in the rail (`01`…`08`) and are stable identifiers, not
 * sort order: an operator on a support call says "the 04 page" and it means something.
 * That is also why `07`/`08` were appended rather than inserted — renumbering would
 * silently change what "the 05 page" refers to in every past conversation.
 */
const routes = [
  {
    path: '/',
    name: 'overview',
    component: () => import('@/views/OverviewView.vue'),
    meta: { title: '总览', titleKey: 'nav.01', index: '01' },
  },
  {
    path: '/runtime',
    name: 'runtime',
    component: () => import('@/views/RuntimeView.vue'),
    meta: { title: '运行状态', titleKey: 'nav.02', index: '02' },
  },
  {
    path: '/plugins',
    name: 'plugins',
    component: () => import('@/views/PluginsView.vue'),
    meta: { title: '插件', titleKey: 'nav.03', index: '03' },
  },
  {
    path: '/security',
    name: 'security',
    component: () => import('@/views/SecurityView.vue'),
    meta: { title: '安全审计', titleKey: 'nav.04', index: '04' },
  },
  {
    path: '/memory',
    name: 'memory',
    component: () => import('@/views/MemoryView.vue'),
    meta: { title: '记忆与知识库', titleKey: 'nav.05', index: '05' },
  },
  {
    path: '/budget',
    name: 'budget',
    component: () => import('@/views/BudgetView.vue'),
    meta: { title: '额度审批', titleKey: 'nav.06', index: '06' },
  },
  {
    path: '/config',
    name: 'config',
    component: () => import('@/views/ConfigView.vue'),
    meta: { title: '模型与人格', titleKey: 'nav.07', index: '07' },
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('@/views/LogsView.vue'),
    meta: { title: '运行日志', titleKey: 'nav.08', index: '08' },
  },
  // 09 and 10 are appended, never inserted. The numbering is a stable identifier used
  // in conversation ("the 04 page"); renumbering to keep a tidy grouping would change
  // what every past reference points at.
  {
    path: '/pipeline',
    name: 'pipeline',
    component: () => import('@/views/PipelineView.vue'),
    meta: { title: '流水线追踪', titleKey: 'nav.09', index: '09' },
  },
  {
    path: '/metrics',
    name: 'metrics',
    component: () => import('@/views/MetricsView.vue'),
    meta: { title: '运行指标', titleKey: 'nav.10', index: '10' },
  },
  {
    path: '/market',
    name: 'market',
    component: () => import('@/views/MarketView.vue'),
    meta: { title: '插件包安装', titleKey: 'nav.11', index: '11' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '系统设置', titleKey: 'nav.12', index: '12' },
  },
  // Anything else falls back to the overview rather than showing a dead end in a tool
  // with eight pages and no deep links.
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  const key = to.meta.titleKey as string | undefined
  const title = key ? t(key) : ((to.meta.title as string | undefined) ?? t('app.console'))
  document.title = `${title} · soapbot`
})

// A language switch has to update the tab title too, or the browser keeps showing the
// previous language until the next navigation — the one place the old language survives
// a switch and looks like a partial translation.
watch(locale, () => {
  const current = router.currentRoute.value
  const key = current.meta.titleKey as string | undefined
  const title = key ? t(key) : ((current.meta.title as string | undefined) ?? t('app.console'))
  document.title = `${title} · soapbot`
})
