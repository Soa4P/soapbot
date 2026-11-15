<script setup lang="ts">
import { computed, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import CommunityPlugins from '@/components/CommunityPlugins.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { t } from '@/i18n'
import { useAsync } from '@/lib/useAsync'

const listing = useAsync(() => api.plugins())

const actionError = ref('')
const busy = ref('')
const approving = ref('')
const selected = ref<string[]>([])

/**
 * The action awaiting confirmation, and which plugin it applies to.
 *
 * Both actions are destructive in different ways — revoke keeps the running instance and
 * changes what happens on the next start; delete removes the directory. `window.confirm`
 * could not express that difference, and it renders outside the focus trap.
 */
type PendingAction =
  | { kind: 'revoke'; plugin: any }
  | { kind: 'delete'; plugin: any }

const pendingAction = ref<PendingAction | null>(null)

const actionDialog = computed(() => {
  const target = pendingAction.value
  if (!target) return { open: false, title: '', detail: '' }
  if (target.kind === 'revoke') {
    // Whether the plugin is running right now changes what revoking means, so the note
    // is chosen at open time rather than baked into one generic sentence.
    const note = target.plugin.loaded
      ? t('plugins.revokeNoteRunning')
      : t('plugins.revokeNoteStopped')
    return {
      open: true,
      title: t('plugins.revokeTitle'),
      detail: `${t('plugins.revokeConfirm', { name: target.plugin.name })} ${note}`,
    }
  }
  return {
    open: true,
    title: t('plugins.deleteTitle'),
    detail: t('plugins.deleteConfirm', { name: target.plugin.name }),
  }
})

function askAction(target: PendingAction): void {
  pendingAction.value = target
}

async function confirmAction(): Promise<void> {
  const target = pendingAction.value
  if (!target) return
  if (target.kind === 'revoke') await revokePlugin(target.plugin)
  else await deletePlugin(target.plugin)
  pendingAction.value = null
}

/**
 * Three tabs rather than one list, because the three groups carry different promises.
 * "Official" means reviewed with the release; "community" means a JSON file somewhere
 * says it exists; "installed" means it is on this disk right now. Flattening them into
 * one table lets an operator read the middle one as if it were the first.
 */
type Tab = 'official' | 'community' | 'installed'
const tab = ref<Tab>('installed')

/** Sensitive capabilities get an explicit warning, not just a checkbox. */
const RISKY = new Set(['http', 'memory_read', 'kb_read', 'send', 'storage', 'cron', 'bilibili'])

const installed = computed<any[]>(() => listing.data.value?.installed ?? [])
const exported = computed<any[]>(() => installed.value.filter((p) => p.api))

/**
 * `channel` is a label from the manifest, not a trust decision — the server never reads
 * it when deciding what to load. A plugin that omits it lands in community, which is the
 * weaker claim, so a forgotten field cannot make something look reviewed.
 */
const official = computed<any[]>(() => installed.value.filter((p) => p.channel === 'official'))
const communityInstalled = computed<any[]>(() =>
  installed.value.filter((p) => p.channel !== 'official'),
)

/** The rows the table shows. The table markup is shared; only the source changes. */
const visible = computed<any[]>(() => {
  if (tab.value === 'official') return official.value
  if (tab.value === 'community') return communityInstalled.value
  return installed.value
})

/**
 * Counts are shown on the two installed tabs only. The community tab's count lives in
 * the catalogue, which is fetched lazily by its own component — putting a number here
 * would mean fetching the index just to render a tab label, and a slow index would then
 * delay a page that has nothing to do with it.
 */
const tabs = computed(() => [
  { id: 'official' as Tab, label: 'plugins.tabOfficial', count: official.value.length },
  { id: 'community' as Tab, label: 'plugins.tabCommunity', count: communityInstalled.value.length },
  { id: 'installed' as Tab, label: 'plugins.tabInstalled', count: installed.value.length },
])

/** `trust` is free text from the manifest; only the declared value is meaningful. */
function trustLabel(value: string): string {
  return value === 'trusted' ? t('plugins.trusted') : t('plugins.untrusted')
}

async function act(name: string, action: 'load' | 'unload'): Promise<void> {
  actionError.value = ''
  busy.value = `${action}:${name}`
  try {
    if (action === 'load') await api.loadPlugin(name)
    else await api.unloadPlugin(name)
    await listing.reload()
  } catch (err) {
    actionError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = ''
  }
}

function startApprove(plugin: any): void {
  approving.value = plugin.name
  selected.value = []
  actionError.value = ''
}

function toggle(capability: string): void {
  const index = selected.value.indexOf(capability)
  if (index >= 0) selected.value.splice(index, 1)
  else selected.value.push(capability)
}

async function confirmApprove(name: string): Promise<void> {
  if (!selected.value.length) return
  actionError.value = ''
  busy.value = `approve:${name}`
  try {
    await api.approvePlugin(name, [...selected.value])
    approving.value = ''
    await listing.reload()
  } catch (err) {
    actionError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = ''
  }
}

/**
 * Withdraw approval without unloading.
 *
 * Confirmed, because the effect is not visible until the next restart: the plugin
 * keeps running now and simply will not start again. A silent button would let an
 * operator believe they had stopped something they had not, and vice versa.
 */
async function revokePlugin(plugin: any): Promise<void> {
  actionError.value = ''
  busy.value = `revoke:${plugin.name}`
  try {
    await api.revokePlugin(plugin.name)
    await listing.reload()
  } catch (err) {
    actionError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = ''
  }
}

/** Permanently remove a plugin's files. Loaded plugins are unloaded server-side first. */
async function deletePlugin(plugin: any): Promise<void> {
  actionError.value = ''
  busy.value = `delete:${plugin.name}`
  try {
    await api.deletePlugin(plugin.name)
    await listing.reload()
  } catch (err) {
    actionError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div class="warn-banner">
    {{ t('plugins.warning') }}
  </div>

  <div v-if="actionError" class="error-banner">{{ actionError }}</div>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('common.plugins') }}</h2>
      <span class="tag">{{ installed.length }}</span>
      <span class="strip__spacer" />
      <div class="segmented" role="tablist" :aria-label="t('common.plugins')">
        <button
          v-for="item in tabs"
          :key="item.id"
          class="segmented__item"
          :class="{ 'segmented__item--on': tab === item.id }"
          type="button"
          role="tab"
          :aria-selected="tab === item.id"
          @click="tab = item.id"
        >
          {{ t(item.label) }}
          <span v-if="item.count !== null" class="segmented__count">{{ item.count }}</span>
        </button>
      </div>
    </div>

    <div v-if="tab === 'community'" class="panel__body">
      <CommunityPlugins />
    </div>

    <div v-else class="panel__body flush">
      <p v-if="tab === 'official'" class="hint" style="padding: 10px 16px 0">
        {{ t('plugins.officialNote') }}
      </p>
      <table v-if="visible.length" class="data"><caption class="visually-hidden">{{ t('common.plugins') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('common.plugin') }}</th>
            <th scope="col">{{ t('common.version') }}</th>
            <th scope="col">{{ t('plugins.trust') }}</th>
            <th scope="col">{{ t('plugins.declared') }}</th>
            <th scope="col">{{ t('plugins.granted') }}</th>
            <th scope="col">{{ t('common.status') }}</th>
            <th scope="col">{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="plugin in visible" :key="plugin.name">
            <tr>
              <td class="key">
                {{ plugin.name }}
                <span class="tag" style="margin-left: 6px">
                  {{ plugin.channel === 'official' ? t('plugins.channelOfficial') : t('plugins.channelCommunity') }}
                </span>
              </td>
              <td>{{ plugin.version || '—' }}</td>
              <td>
                <span class="tag" :class="plugin.trust === 'trusted' ? '' : 'bad'">
                  {{ trustLabel(plugin.trust) }}
                </span>
              </td>
              <td>
                <span
                  v-for="cap in plugin.capabilities"
                  :key="cap"
                  class="tag"
                  :class="RISKY.has(cap) ? 'bad' : ''"
                  style="margin-right: 4px"
                >
                  {{ cap }}
                </span>
              </td>
              <td>
                <span v-if="plugin.approved" class="tag lamp">
                  {{ plugin.pending.length ? t('plugins.partial') : t('plugins.full') }}
                </span>
                <span v-else class="faint">{{ t('plugins.notApproved') }}</span>
                <!-- 有新版本：索引声明了比已装版本更新的 latest（数字段比较，
                     非法版本不显示——「无法判断」绝不渲染成「有更新」）。 -->
                <span v-if="plugin.update_available" class="tag" :title="t('plugins.updateHint')">
                  {{ t('plugins.updateAvailable') }}
                </span>
                <!-- Code changed after approval. Shown here, before anyone presses Load:
                     the server enforces it on load (block by default), and learning about
                     it from a failed load with a stack trace is the wrong first notice. -->
                <span
                  v-if="plugin.approval?.code_changed"
                  class="tag bad"
                  :title="t('plugins.codeChangedHint', { mode: plugin.approval.integrity_mode })"
                >
                  {{ t('plugins.codeChanged') }}
                </span>
                <!-- A version blocked *after* it was installed. Not auto-uninstalled:
                     deleting running code because a list changed is its own outage. But
                     "known bad and still running" is exactly what an operator must see. -->
                <span
                  v-if="plugin.blocked"
                  class="tag bad"
                  :title="t('plugins.blockedReason', { reason: plugin.blocked.reason })"
                >
                  {{ t('plugins.installedBlocked', { version: plugin.blocked.version }) }}
                </span>
              </td>
              <td>
                <span class="pill" :class="plugin.loaded ? 'ok' : ''">
                  <i class="dot" />{{ plugin.loaded ? t('plugins.running') : t('plugins.notLoaded') }}
                </span>
              </td>
              <td>
                <div class="row">
                  <button
                    v-if="!plugin.loaded"
                    class="btn"
                    :disabled="busy !== '' || !plugin.pending.length"
                    :title="plugin.pending.length ? '' : t('plugins.approveHint')"
                    @click="startApprove(plugin)"
                  >
                    {{ t('plugins.approve') }}
                  </button>
                  <button
                    v-if="plugin.approved && !plugin.loaded"
                    class="btn lamp"
                    :disabled="
                      busy !== '' ||
                      (plugin.approval?.code_changed && plugin.approval?.integrity_mode === 'block')
                    "
                    :title="
                      plugin.approval?.code_changed && plugin.approval?.integrity_mode === 'block'
                        ? t('plugins.codeChangedHint', { mode: plugin.approval.integrity_mode })
                        : ''
                    "
                    @click="act(plugin.name, 'load')"
                  >
                    {{ t('plugins.load') }}
                  </button>
                  <button
                    v-if="plugin.loaded"
                    class="btn ghost"
                    :disabled="busy !== ''"
                    @click="act(plugin.name, 'unload')"
                  >
                    {{ t('plugins.unload') }}
                  </button>
                  <button
                    v-if="plugin.approved"
                    class="btn ghost"
                    :disabled="busy !== ''"
                    :title="t('plugins.revokeTitle')"
                    @click="askAction({ kind: 'revoke', plugin })"
                  >
                    {{ t('plugins.revoke') }}
                  </button>
                  <button
                    class="btn ghost"
                    :disabled="busy !== ''"
                    :title="t('plugins.deleteTitle')"
                    @click="askAction({ kind: 'delete', plugin })"
                  >
                    {{ t('common.delete') }}
                  </button>
                </div>
              </td>
            </tr>

            <tr v-if="approving === plugin.name">
              <td colspan="7">
                <div class="stack" style="padding: 4px 0">
                  <div class="eyebrow">
                    {{ t('plugins.selectCaps', { name: plugin.name }) }}
                  </div>
                  <div class="row">
                    <label
                      v-for="cap in plugin.pending"
                      :key="cap"
                      class="tag"
                      :class="[
                        RISKY.has(cap) ? 'bad' : '',
                        selected.includes(cap) ? 'lamp' : '',
                      ]"
                      style="cursor: pointer"
                    >
                      <input
                        type="checkbox"
                        :checked="selected.includes(cap)"
                        style="margin-right: 6px"
                        @change="toggle(cap)"
                      />
                      {{ cap }}
                    </label>
                  </div>
                  <div class="row">
                    <button
                      class="btn lamp"
                      :disabled="!selected.length || busy !== ''"
                      @click="confirmApprove(plugin.name)"
                    >
                      {{ t('plugins.confirmApprove') }}
                    </button>
                    <button class="btn ghost" @click="approving = ''">{{ t('common.cancel') }}</button>
                  </div>
                  <!-- One capability per line, each with a whole sentence. The previous
                       version interleaved three code tokens into one sentence, which is
                       exactly the shape that cannot be translated without reordering. -->
                  <ul class="hint" style="margin: 0; padding-left: 18px">
                    <li><span class="mono">http</span> — {{ t('plugins.cap.http') }}</li>
                    <li><span class="mono">memory_read / kb_read</span> — {{ t('plugins.cap.read') }}</li>
                    <li><span class="mono">send</span> — {{ t('plugins.cap.send') }}</li>
                    <li><span class="mono">send_media / media_observe</span> — {{ t('plugins.cap.media') }}</li>
                    <li><span class="mono">browse</span> — {{ t('plugins.cap.browse') }}</li>
                    <li><span class="mono">qzone_read / qzone_write</span> — {{ t('plugins.cap.qzone') }}</li>
                  </ul>
                  <p class="hint" style="margin: 0">{{ t('plugins.grantReplaces') }}</p>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <!-- The empty state names the tab that is empty. "No plugins installed" on the
           official tab is misleading when three community plugins are installed. The
           community tab has no table at all — it renders `CommunityPlugins` — so only
           these two branches are reachable. -->
      <div v-else class="empty">
        <template v-if="tab === 'official'">{{ t('plugins.officialEmpty') }}</template>
        <template v-else>
          {{ t('plugins.empty') }}
          <div class="mono" style="margin-top: 6px">data/plugins/&lt;name&gt;/plugin.yaml</div>
        </template>
      </div>
    </div>
  </section>

  <section v-if="exported.length" class="panel">
    <div class="panel__head">
      <h2>{{ t('plugins.exported') }}</h2>
      <span class="tag">{{ exported.length }}</span>
    </div>
    <div class="panel__body flush">
      <table class="data"><caption class="visually-hidden">{{ t('plugins.exported') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('common.plugin') }}</th>
            <th scope="col">{{ t('plugins.commands') }}</th>
            <th scope="col">{{ t('common.tools') }}</th>
            <th scope="col">{{ t('plugins.cronJobs') }}</th>
            <th scope="col" class="num">{{ t('common.calls') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="plugin in exported" :key="plugin.name">
            <td class="key">{{ plugin.name }}</td>
            <td>{{ (plugin.api?.commands ?? []).join(', ') || '—' }}</td>
            <td>{{ (plugin.api?.tools ?? []).join(', ') || '—' }}</td>
            <td>{{ (plugin.api?.cron_jobs ?? []).join(', ') || '—' }}</td>
            <td class="num">{{ plugin.invocations ?? 0 }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <div v-if="listing.error.value" class="error-banner">{{ listing.error.value }}</div>

  <ConfirmDialog
    :open="actionDialog.open"
    :title="actionDialog.title"
    :detail="actionDialog.detail"
    tone="danger"
    :irreversible="pendingAction?.kind === 'delete'"
    :busy="busy !== ''"
    @confirm="confirmAction"
    @cancel="pendingAction = null"
  />
</template>
