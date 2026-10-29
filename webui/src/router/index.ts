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
    meta: { titleKey: 'nav.01', index: '01' },
  },
  {
    path: '/runtime',
    name: 'runtime',
    component: () => import('@/views/RuntimeView.vue'),
    meta: { titleKey: 'nav.02', index: '02' },
  },
  {
    path: '/plugins',
    name: 'plugins',
    component: () => import('@/views/PluginsView.vue'),
    meta: { titleKey: 'nav.03', index: '03' },
  },
  {
    path: '/security',
    name: 'security',
    component: () => import('@/views/SecurityView.vue'),
    meta: { titleKey: 'nav.04', index: '04' },
  },
  {
    path: '/memory',
    name: 'memory',
    component: () => import('@/views/MemoryView.vue'),
    meta: { titleKey: 'nav.05', index: '05' },
  },
  {
    path: '/budget',
    name: 'budget',
    component: () => import('@/views/BudgetView.vue'),
    meta: { titleKey: 'nav.06', index: '06' },
  },
  {
    path: '/config',
    name: 'config',
    component: () => import('@/views/ConfigView.vue'),
    meta: { titleKey: 'nav.07', index: '07' },
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('@/views/LogsView.vue'),
    meta: { titleKey: 'nav.08', index: '08' },
  },
  // 09 and 10 are appended, never inserted. The numbering is a stable identifier used
  // in conversation ("the 04 page"); renumbering to keep a tidy grouping would change
  // what every past reference points at.
  {
    path: '/pipeline',
    name: 'pipeline',
    component: () => import('@/views/PipelineView.vue'),
    meta: { titleKey: 'nav.09', index: '09' },
  },
  {
    path: '/metrics',
    name: 'metrics',
    component: () => import('@/views/MetricsView.vue'),
    meta: { titleKey: 'nav.10', index: '10' },
  },
  {
    path: '/market',
    name: 'market',
    component: () => import('@/views/MarketView.vue'),
    meta: { titleKey: 'nav.11', index: '11' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { titleKey: 'nav.12', index: '12' },
  },
  // Anything else falls back to the overview rather than showing a dead end in a tool
  // with eight pages and no deep links.
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

/**
 * Title for the tab. `titleKey` only — there used to be a Chinese `title` beside it as a
 * fallback, which meant the tab kept the old language whenever the key was missing.
 * One source, and a missing key shows up as the key rather than as stale Chinese.
 */
function pageTitle(key: string | undefined): string {
  return key ? t(key) : t('app.console')
}

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${pageTitle(to.meta.titleKey as string | undefined)} · soapbot`
})

// A language switch has to update the tab title too, or the browser keeps showing the
// previous language until the next navigation — the one place the old language survives
// a switch and looks like a partial translation.
watch(locale, () => {
  document.title = `${pageTitle(router.currentRoute.value.meta.titleKey as string | undefined)} · soapbot`
})
