<script setup lang="ts">
import { computed, ref } from 'vue'

import { ApiError, api } from '@/api/client'
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
  const note = plugin.loaded
    ? '将保留当前运行实例，但下次启动不会再加载。'
    : '该插件当前未运行，撤销后也不会再自动加载。'
  if (!window.confirm(`撤销对「${plugin.name}」的批准？\n${note}`)) return
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
  if (
    !window.confirm(
      `永久删除插件「${plugin.name}」的目录？此操作会同时撤销批准，无法通过界面恢复。`,
    )
  )
    return
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
    加载插件等于在本进程内执行第三方代码。列表只做发现，不会自动加载任何插件。
  </div>

  <div v-if="actionError" class="error-banner">{{ actionError }}</div>

  <section class="panel">
    <div class="panel__head">
      <h2>已安装</h2>
      <span class="tag">{{ installed.length }}</span>
      <span class="strip__spacer" />
      <span class="hint">批准是按能力逐项授予的</span>
    </div>
    <div class="panel__body flush">
      <table v-if="installed.length" class="data"><caption class="visually-hidden">已安装</caption>
        <thead>
          <tr>
            <th scope="col">插件</th>
            <th scope="col">版本</th>
            <th scope="col">信任</th>
            <th scope="col">声明能力</th>
            <th scope="col">已授权</th>
            <th scope="col">状态</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="plugin in installed" :key="plugin.name">
            <tr>
              <td class="key">{{ plugin.name }}</td>
              <td>{{ plugin.version || '—' }}</td>
              <td>
                <span class="tag" :class="plugin.trust === 'trusted' ? '' : 'bad'">
                  {{ plugin.trust || 'untrusted' }}
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
                <span v-if="plugin.approved" class="tag lamp">{{ plugin.pending.length ? '部分' : '全部' }}</span>
                <span v-else class="faint">未授权</span>
              </td>
              <td>
                <span class="pill" :class="plugin.loaded ? 'ok' : ''">
                  <i class="dot" />{{ plugin.loaded ? '运行中' : '未加载' }}
                </span>
              </td>
              <td>
                <div class="row">
                  <button
                    v-if="!plugin.loaded"
                    class="btn"
                    :disabled="busy !== '' || !plugin.pending.length"
                    :title="plugin.pending.length ? '' : '先授权至少一项能力'"
                    @click="startApprove(plugin)"
                  >
                    授权…
                  </button>
                  <button
                    v-if="plugin.approved && !plugin.loaded"
                    class="btn lamp"
                    :disabled="busy !== ''"
                    @click="act(plugin.name, 'load')"
                  >
                    加载
                  </button>
                  <button
                    v-if="plugin.loaded"
                    class="btn ghost"
                    :disabled="busy !== ''"
                    @click="act(plugin.name, 'unload')"
                  >
                    卸载
                  </button>
                  <button
                    v-if="plugin.approved"
                    class="btn ghost"
                    :disabled="busy !== ''"
                    title="保留当前实例，但下次启动不再自动加载"
                    @click="revoke(plugin)"
                  >
                    撤销批准
                  </button>
                  <button
                    class="btn ghost"
                    :disabled="busy !== ''"
                    title="删除插件目录，无法通过界面恢复"
                    @click="remove(plugin)"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>

            <tr v-if="approving === plugin.name">
              <td colspan="7">
                <div class="stack" style="padding: 4px 0">
                  <div class="eyebrow">
                    选择要授予 {{ plugin.name }} 的能力（未声明的能力无法授予）
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
                      确认授权
                    </button>
                    <button class="btn ghost" @click="approving = ''">取消</button>
                  </div>
                  <p class="hint" style="margin: 0">
                    <span class="mono">http</span> 允许外发请求，
                    <span class="mono">memory_read / kb_read</span> 可读取会话与文档，
                    <span class="mono">send</span> 可主动发消息。授权是替换而不是合并。
                  </p>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div v-else class="empty">
        插件目录为空。<span class="mono">data/plugins/&lt;name&gt;/plugin.yaml</span>
      </div>
    </div>
  </section>

  <section v-if="exported.length" class="panel">
    <div class="panel__head">
      <h2>运行中插件导出</h2>
      <span class="tag">{{ exported.length }}</span>
    </div>
    <div class="panel__body flush">
      <table class="data"><caption class="visually-hidden">运行中插件导出</caption>
        <thead>
          <tr>
            <th scope="col">插件</th>
            <th scope="col">命令</th>
            <th scope="col">工具</th>
            <th scope="col">定时任务</th>
            <th scope="col" class="num">调用</th>
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
