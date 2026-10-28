<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { datetime, fromNow, num, truncate } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const sessions = useAsync(() => api.memorySessions(100))
const stats = useAsync(() => api.memoryStats())
const knowledge = useAsync(() => api.knowledge())

const selected = ref('')
const timeline = ref<any[]>([])
const timelineError = ref('')
const timelineLoading = ref(false)

async function openSession(key: string): Promise<void> {
  selected.value = key
  timelineLoading.value = true
  timelineError.value = ''
  try {
    const result = await api.memoryTimeline(key, 80)
    timeline.value = result.messages ?? []
  } catch (err) {
    timelineError.value = (err as Error).message
    timeline.value = []
  } finally {
    timelineLoading.value = false
  }
}

const rows = computed<any[]>(() => sessions.data.value?.sessions ?? [])

const layerRows = computed(() => {
  const layers = stats.data.value?.layers ?? {}
  return Object.entries(layers).map(([name, count]) => ({ name, count: Number(count) }))
})

const documents = computed<any[]>(() => knowledge.data.value?.documents ?? [])

function roleLabel(role: string): string {
  return role === 'assistant' ? '机器人' : '用户'
}

// ---------------------------------------------------------------- knowledge write
//
// The panel used to say "上传接口尚未开放". It now exists, so the panel that
// advertises it has to be able to use it — a UI that describes a capability it
// cannot reach is indistinguishable from a missing feature.
const draftTitle = ref('')
const draftContent = ref('')
const draftId = ref('')
const saving = ref(false)
const saveError = ref('')
const saveNotice = ref('')

async function submitDocument(): Promise<void> {
  saveError.value = ''
  saveNotice.value = ''
  if (!draftTitle.value.trim() || !draftContent.value.trim()) {
    saveError.value = '标题和正文都不能为空。'
    return
  }
  saving.value = true
  try {
    const result = await api.ingestKnowledge({
      title: draftTitle.value.trim(),
      content: draftContent.value,
      doc_id: draftId.value.trim() || undefined,
    })
    saveNotice.value = result.replaced
      ? `已替换文档 ${result.doc_id}，共 ${result.chunks} 个片段。`
      : `已创建文档 ${result.doc_id}，共 ${result.chunks} 个片段。`
    draftContent.value = ''
    draftId.value = result.doc_id
    await knowledge.reload()
  } catch (err) {
    saveError.value = (err as Error).message
  } finally {
    saving.value = false
  }
}

function editDocument(doc: any): void {
  draftId.value = doc.doc_id
  draftTitle.value = doc.title || ''
  draftContent.value = ''
  saveNotice.value = '已载入文档 ID 与标题；粘贴新正文后提交即覆盖原文档。'
  saveError.value = ''
}

async function removeDocument(doc: any): Promise<void> {
  if (!window.confirm(`删除文档「${doc.title || doc.doc_id}」及其全部片段？`)) return
  saveError.value = ''
  saveNotice.value = ''
  try {
    const result = await api.deleteKnowledge(doc.doc_id)
    saveNotice.value = `已删除 ${result.chunks_removed} 个片段。`
    if (draftId.value === doc.doc_id) {
      draftId.value = ''
      draftTitle.value = ''
    }
    await knowledge.reload()
  } catch (err) {
    saveError.value = (err as Error).message
  }
}

function resetDraft(): void {
  draftId.value = ''
  draftTitle.value = ''
  draftContent.value = ''
  saveNotice.value = ''
  saveError.value = ''
}
</script>

<template>
  <div class="grid cols-3">
    <div class="readout">
      <span class="readout__label">记忆条目</span>
      <span class="readout__value">{{ num(stats.data.value?.total) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">会话数</span>
      <span class="readout__value">{{ num(rows.length) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">知识文档</span>
      <span class="readout__value">{{ num(documents.length) }}</span>
    </div>
  </div>

  <div class="grid cols-2">
    <section class="panel">
      <div class="panel__head">
        <h2>会话</h2>
        <span class="hint">点击查看时间线</span>
      </div>
      <div class="panel__body flush">
        <div class="scroll">
          <table v-if="rows.length" class="data"><caption class="visually-hidden">会话</caption>
            <thead>
              <tr>
                <th scope="col">会话</th>
                <th scope="col" class="num">消息</th>
                <th scope="col">最近</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in rows"
                :key="row.session_key"
                style="cursor: pointer"
                :style="selected === row.session_key ? 'background: var(--brand-soft)' : ''"
                @click="openSession(row.session_key)"
              >
                <td class="key">{{ row.session_key }}</td>
                <td class="num">{{ num(row.message_count) }}</td>
                <td>{{ row.last_at ? fromNow(row.last_at) : '—' }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">还没有归档的会话。机器人收到消息后才会出现。</div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h2>记忆分层</h2>
      </div>
      <div class="panel__body flush">
        <table v-if="layerRows.length" class="data"><caption class="visually-hidden">记忆分层</caption>
          <tbody>
            <tr v-for="layer in layerRows" :key="layer.name">
              <td class="key">{{ layer.name }}</td>
              <td class="num">{{ layer.count < 0 ? '不可读' : num(layer.count) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">记忆存储未启用。</div>
      </div>
    </section>
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>时间线</h2>
      <span v-if="selected" class="tag lamp">{{ selected }}</span>
      <span class="strip__spacer" />
      <span v-if="timeline.length" class="hint">{{ timeline.length }} 条</span>
    </div>
    <div class="panel__body flush">
      <div v-if="timelineError" class="panel__body">
        <div class="error-banner">{{ timelineError }}</div>
      </div>
      <div v-else-if="timelineLoading" class="empty">载入中…</div>
      <div v-else-if="!selected" class="empty">从左侧选择一个会话。</div>
      <div v-else-if="!timeline.length" class="empty">该会话没有记录。</div>
      <div v-else class="scroll">
        <table class="data"><caption class="visually-hidden">时间线</caption>
          <thead>
            <tr>
              <th scope="col">时间</th>
              <th scope="col">角色</th>
              <th scope="col">内容</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in timeline" :key="index">
              <td style="white-space: nowrap">{{ datetime(row.created_at) }}</td>
              <td>
                <span class="tag" :class="row.role === 'assistant' ? 'lamp' : ''">
                  {{ roleLabel(row.role) }}
                </span>
              </td>
              <td style="max-width: 620px">
                {{ truncate(row.content, 200) || '（空）' }}
                <span v-if="row.image_desc" class="tag" style="margin-left: 6px">图</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>知识库文档</h2>
      <span class="tag">{{ documents.length }}</span>
      <span class="strip__spacer" />
      <button class="btn ghost" @click="resetDraft">新建文档</button>
    </div>
    <div class="panel__body flush">
      <table v-if="documents.length" class="data"><caption class="visually-hidden">知识库文档</caption>
        <thead>
          <tr>
            <th scope="col">标题</th>
            <th scope="col">ID</th>
            <th scope="col" class="num">分段</th>
            <th scope="col" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="doc in documents" :key="doc.doc_id">
            <td class="key">{{ doc.title || '（无标题）' }}</td>
            <td>{{ doc.doc_id }}</td>
            <td class="num">{{ doc.chunks }}</td>
            <td style="white-space: nowrap">
              <button class="btn ghost" @click="editDocument(doc)">替换</button>
              <button class="btn ghost" @click="removeDocument(doc)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">
        知识库为空。在下方填写标题与正文即可写入；机器人会在 `/kb` 与对话中检索这些内容。
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>{{ draftId ? '替换文档' : '新增文档' }}</h2>
      <span v-if="draftId" class="tag lamp">{{ draftId }}</span>
      <span class="strip__spacer" />
      <span class="hint">正文会按段落切分并建立索引</span>
    </div>
    <div class="panel__body">
      <div class="stack">
        <div class="row">
          <input
            v-model="draftTitle"
            class="field"
            style="flex: 1 1 260px"
            placeholder="标题（例如：退换货政策）"
            maxlength="200"
          />
          <input
            v-model="draftId"
            class="field"
            style="flex: 0 1 220px"
            placeholder="文档 ID（留空自动生成）"
            maxlength="64"
          />
        </div>
        <textarea
          v-model="draftContent"
          class="field"
          rows="8"
          placeholder="粘贴正文。留空表示只更新标题不会生效——替换文档时必须重新粘贴正文。"
        />
        <div class="row">
          <button class="btn lamp" :disabled="saving" @click="submitDocument">
            {{ saving ? '写入中…' : draftId ? '覆盖并重建索引' : '写入知识库' }}
          </button>
          <span v-if="saveNotice" class="hint">{{ saveNotice }}</span>
        </div>
        <div v-if="saveError" class="error-banner">{{ saveError }}</div>
      </div>
    </div>
  </section>

  <div v-if="sessions.error.value" class="error-banner">{{ sessions.error.value }}</div>
</template>
