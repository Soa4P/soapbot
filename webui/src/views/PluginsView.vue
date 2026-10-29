<script setup lang="ts">
import { computed, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { t } from '@/i18n'
import { useAsync } from '@/lib/useAsync'

const listing = useAsync(() => api.plugins())

const actionError = ref('')
const busy = ref('')
const approving = ref('')
const selected = ref<string[]>([])

/** Sensitive capabilities get an explicit warning, not just a checkbox. */
const RISKY = new Set(['http', 'memory_read', 'kb_read', 'send', 'storage', 'cron'])

const installed = computed<any[]>(() => listing.data.value?.installed ?? [])
const exported = computed<any[]>(() => installed.value.filter((p) => p.api))

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
async function revoke(plugin: any): Promise<void> {
  const note = plugin.loaded ? t('plugins.revokeNoteRunning') : t('plugins.revokeNoteStopped')
  if (!window.confirm(`${t('plugins.revokeConfirm', { name: plugin.name })}\n${note}`)) return
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
async function remove(plugin: any): Promise<void> {
  if (!window.confirm(t('plugins.deleteConfirm', { name: plugin.name }))) return
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
      <h2>{{ t('common.installed') }}</h2>
      <span class="tag">{{ installed.length }}</span>
      <span class="strip__spacer" />
      <span class="hint">{{ t('plugins.perCapability') }}</span>
    </div>
    <div class="panel__body flush">
      <table v-if="installed.length" class="data"><caption class="visually-hidden">{{ t('common.installed') }}</caption>
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
          <template v-for="plugin in installed" :key="plugin.name">
            <tr>
              <td class="key">{{ plugin.name }}</td>
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
                    :disabled="busy !== ''"
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
                    @click="revoke(plugin)"
                  >
                    {{ t('plugins.revoke') }}
                  </button>
                  <button
                    class="btn ghost"
                    :disabled="busy !== ''"
                    :title="t('plugins.deleteTitle')"
                    @click="remove(plugin)"
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
                  </ul>
                  <p class="hint" style="margin: 0">{{ t('plugins.grantReplaces') }}</p>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div v-else class="empty">
        {{ t('plugins.empty') }}
        <div class="mono" style="margin-top: 6px">data/plugins/&lt;name&gt;/plugin.yaml</div>
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
</template>
