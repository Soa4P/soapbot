<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import { useAsync } from '@/lib/useAsync'

/**
 * Plugin market: the one page where a package arrives from outside.
 *
 * The page is built around a single distinction the backend enforces and the UI must
 * not blur: **installing is not approving**. Uploading writes bytes and makes the
 * plugin discoverable; approving grants named capabilities one at a time. If the
 * cards showed a single "启用" button, the distinction would exist only in the API
 * and an operator would reasonably read "installed" as "running".
 */
const router = useRouter()
const listing = useAsync(() => api.plugins())

const plugins = computed<any[]>(() => listing.data.value?.installed ?? [])
const pending = computed(() => plugins.value.filter((p) => !p.approved).length)
const live = computed(() => plugins.value.filter((p) => p.loaded).length)

const uploading = ref(false)
const dragging = ref(false)
const uploadError = ref('')
const uploadedHere = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

/** Capability risk tiers. Colour never carries the meaning alone: each tag also
 *  prints the tier in text, so the page works without colour perception. */
const HIGH = new Set(['http', 'command', 'cron', 'network', 'exec'])
const MID = new Set(['storage', 'send', 'memory_write', 'write', 'kb_write'])

function tier(cap: string): 'high' | 'mid' | 'low' {
  const name = cap.toLowerCase()
  if (HIGH.has(name)) return 'high'
  if (MID.has(name)) return 'mid'
  return 'low'
}

function tierClass(cap: string): string {
  const t = tier(cap)
  return t === 'high' ? 'tag bad' : t === 'mid' ? 'tag lamp' : 'tag'
}

function tierWord(cap: string): string {
  const t = tier(cap)
  return t === 'high' ? '执行' : t === 'mid' ? '写入' : '读取'
}

async function upload(file: File): Promise<void> {
  uploading.value = true
  uploadError.value = ''
  try {
    const result = await api.installPlugin(file)
    uploadedHere.value = [result.name, ...uploadedHere.value.filter((n) => n !== result.name)]
    await listing.reload()
  } catch (err) {
    uploadError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    uploading.value = false
  }
}

function onFileChosen(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void upload(file)
  input.value = ''
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void upload(file)
}

function openPlugins(): void {
  // Approval lives on the plugin page; sending the operator there is the point of
  // the second action, not a convenience.
  void router.push({ name: 'plugins' })
}
</script>

<template>
  <div class="warn-banner">
    上传即安装，但不等于批准。安装只把文件放进 <span class="mono">data/plugins/</span>，
    插件声明的能力仍需要你在「03 插件」逐项批准后才会生效。
  </div>

  <div v-if="uploadError" class="error-banner">{{ uploadError }}</div>

  <section class="strip">
    <span class="strip__title">插件市场</span>
    <span class="strip__spacer" />
    <span class="hint">批准记录以清单摘要为准，改清单必须重新批准</span>
  </section>

  <div class="grid cols-3">
    <div class="readout">
      <span class="readout__label">已安装</span>
      <span class="readout__value">{{ plugins.length }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">待批准</span>
      <span class="readout__value">{{ pending }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">运行中</span>
      <span class="readout__value">{{ live }}</span>
    </div>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>上传插件包</h2>
      <span class="strip__spacer" />
      <span class="hint">仅接受 zip，含单个目录与一份 plugin.yaml</span>
    </div>
    <div class="panel__body stack">
      <div
        class="row"
        style="justify-content: space-between; gap: 16px"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <div class="stack" style="gap: 4px">
          <strong>{{ dragging ? '松开以安装' : '把插件压缩包拖到这里' }}</strong>
          <span class="faint">
            校验顺序：包结构 → 路径与体积 → 清单复核 → 落盘。任一步失败都不会留下半个目录。
          </span>
        </div>
        <button class="btn lamp" :disabled="uploading" @click="fileInput?.click()">
          {{ uploading ? '正在安装…' : '选择文件' }}
        </button>
        <input
          ref="fileInput"
          class="visually-hidden"
          type="file"
          accept=".zip,application/zip"
          @change="onFileChosen"
        />
      </div>

      <div class="row" style="gap: 12px">
        <span class="hint">能力风险：</span>
        <span class="tag bad">执行</span>
        <span class="hint">会触达网络或在本进程执行命令</span>
        <span class="tag lamp">写入</span>
        <span class="hint">会改动存储或对外发送</span>
        <span class="tag">读取</span>
        <span class="hint">只读数据</span>
      </div>

      <p v-if="uploadedHere.length" class="hint">
        本次已安装：{{ uploadedHere.join('、') }} —— 下一步请到「03 插件」批准所需能力。
      </p>
    </div>
  </section>

  <section v-if="plugins.length" class="grid cols-2">
    <article v-for="plugin in plugins" :key="plugin.name" class="panel">
      <div class="panel__head">
        <h2>{{ plugin.name }}</h2>
        <span class="tag">{{ plugin.version || '0.0.0' }}</span>
        <span class="strip__spacer" />
        <span class="tag" :class="plugin.trust === 'trusted' ? 'ok' : 'bad'">
          {{ plugin.trust || 'untrusted' }}
        </span>
      </div>
      <div class="panel__body stack">
        <p class="faint" style="margin: 0">
          {{ plugin.description || '该插件没有填写说明。' }}
        </p>

        <div class="row" style="flex-wrap: wrap; gap: 6px">
          <span v-if="!plugin.capabilities?.length" class="faint">未声明任何能力</span>
          <span
            v-for="cap in plugin.capabilities"
            :key="cap"
            :class="tierClass(cap)"
            :title="`风险等级：${tierWord(cap)}`"
          >
            {{ cap }} · {{ tierWord(cap) }}
          </span>
        </div>

        <div class="row">
          <span class="pill" :class="plugin.approved ? 'ok' : 'warn'">
            <i class="dot" />{{ plugin.approved ? '已批准' : '待批准' }}
          </span>
          <span class="pill" :class="plugin.loaded ? 'ok' : ''">
            <i class="dot" />{{ plugin.loaded ? '运行中' : '未加载' }}
          </span>
          <span class="strip__spacer" />
          <button class="btn ghost" @click="openPlugins()">
            {{ plugin.approved ? '查看' : '去批准' }}
          </button>
        </div>

        <p v-if="plugin.pending?.length" class="hint" style="margin: 0">
          尚未授权：{{ plugin.pending.join('、') }}
        </p>
      </div>
    </article>
  </section>

  <section v-else class="panel">
    <div class="panel__head"><h2>还没有插件</h2></div>
    <div class="panel__body">
      <div class="empty">
        <p>上传一个 zip，或手动放到服务器的目录里：</p>
        <pre class="mono" style="margin: 0; white-space: pre-wrap">data/plugins/
└── demo/
    ├── plugin.yaml   # name / version / entry / capabilities
    └── main.py</pre>
        <p class="hint">
          手动放置后刷新本页即可发现；能力同样需要逐项批准。
        </p>
      </div>
    </div>
  </section>
</template>
