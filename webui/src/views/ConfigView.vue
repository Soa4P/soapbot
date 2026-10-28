<script setup lang="ts">
import { computed, ref } from 'vue'

import { api, type DiffResult, type ProviderEntry, type ProvidersDocument, type ProvidersPatch } from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DiffEditor from '@/components/DiffEditor.vue'
import { num, truncate } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

/**
 * 07 — providers and personas.
 *
 * This page was read-only by design, and the reasoning was that identity and failover
 * target are configuration which belongs in a reviewed file. That reasoning still holds;
 * what changed is where the review happens. Editing here goes through three steps —
 * read, diff, apply — so the operator sees the exact lines that will change and confirms
 * them, and the change is written to the audit log. A file edited over SSH had neither.
 *
 * The personas section stays read-only in this pass. Persona cards are Markdown with
 * front matter, and a form that renders them as fields would silently drop the prose
 * between the front matter and the body — a worse outcome than leaving the section
 * informative but not editable.
 */
const providers = useAsync(() => api.providers())
const personas = useAsync(() => api.personas())

const providerRows = computed<any[]>(() => providers.data.value?.providers ?? [])
const stats = computed<Record<string, any>>(() => providers.data.value?.stats ?? {})
const personaRows = computed<any[]>(() => personas.data.value?.personas ?? [])
const binding = computed<any>(() => personas.data.value?.binding ?? {})

const expanded = ref('')
function toggle(id: string): void {
  expanded.value = expanded.value === id ? '' : id
}

function statFor(id: string): any {
  return stats.value[id] ?? {}
}

/* ------------------------------------------------------------- write flow */

const document = ref<ProvidersDocument | null>(null)
const drafts = ref<ProviderEntry[]>([])
const baseHash = ref('')
const edited = ref<Record<string, boolean>>({})
const loadError = ref('')
const flowError = ref('')
const busy = ref(false)

const diff = ref<DiffResult | null>(null)
const showDiff = ref(false)
const restartNeeded = ref(false)
const appliedFields = ref<string[]>([])

const hasEdits = computed(() => Object.values(edited.value).some(Boolean))

const mask = computed(() => document.value?.mask ?? '********')
const sentinel = computed(() => document.value?.unchanged_sentinel ?? '__UNCHANGED__')

async function loadForEdit(): Promise<void> {
  busy.value = true
  loadError.value = ''
  try {
    const body = await api.configProviders()
    document.value = body
    baseHash.value = body.base_hash
    // Deep copy: the draft must be independent of `document`, or a rejected diff
    // leaves the "current" view showing edits that were never written.
    drafts.value = JSON.parse(JSON.stringify(body.document.providers ?? []))
    edited.value = {}
    diff.value = null
    showDiff.value = false
  } catch (err) {
    // Parse failures arrive here as 422 with the YAML error. Showing an empty form
    // instead would invite the operator to "save" over a file that merely had a typo.
    loadError.value = (err as Error).message
  } finally {
    busy.value = false
  }
}

function markEdited(id: string): void {
  edited.value = { ...edited.value, [id]: true }
}

function onSecretInput(row: ProviderEntry, event: Event): void {
  const value = (event.target as HTMLInputElement).value
  row.api_key = value
  markEdited(row.id)
}

function addRow(): void {
  const id = `provider-${drafts.value.length + 1}`
  drafts.value.push({
    id,
    kind: 'openai_compat',
    base_url: '',
    api_key: sentinel.value,
    model: '',
    priority: (drafts.value.length + 1) * 10,
    enabled: true,
  })
  markEdited(id)
}

function removeRow(index: number): void {
  // Deleting a provider is not supported by the patch protocol on purpose: the apply
  // endpoint merges, so a row dropped from the payload would survive. Saying so is
  // better than a button that appears to work and does nothing.
  flowError.value =
    '删除 Provider 请直接改文件后重启：写入接口按 id 合并，仅凭表单无法表达「删除」这个意图。'
  drafts.value.splice(index, 1)
}

function payload(): ProvidersPatch {
  return {
    base_hash: baseHash.value,
    // Only edited rows are sent. Every field is included for those rows so a cleared
    // field actually clears; untouched rows are omitted so they cannot be clobbered by
    // a field the form does not render.
    providers: drafts.value
      .filter((row) => edited.value[row.id])
      .map((row) => ({ ...row, id: row.id ?? '' })),
  }
}

async function previewDiff(): Promise<void> {
  if (!hasEdits.value) {
    flowError.value = '还没有任何改动。'
    return
  }
  busy.value = true
  flowError.value = ''
  try {
    const body = await api.configProvidersDiff(payload())
    diff.value = body
    showDiff.value = true
  } catch (err) {
    flowError.value = (err as Error).message
  } finally {
    busy.value = false
  }
}

const confirmOpen = ref(false)

function requestApply(): void {
  confirmOpen.value = true
}

async function applyChanges(): Promise<void> {
  if (!diff.value) return
  busy.value = true
  flowError.value = ''
  try {
    const body = await api.configProvidersApply({
      ...payload(),
      approved_hash: diff.value.new_hash,
    })
    if (!body.written) {
      flowError.value = `未写入：${body.reason ?? '没有改动'}`
      return
    }
    appliedFields.value = body.changed_fields
    restartNeeded.value = body.restart_required === true
    confirmOpen.value = false
    showDiff.value = false
    diff.value = null
    edited.value = {}
    await loadForEdit()
    providers.reload()
  } catch (err) {
    flowError.value = (err as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="grid cols-3">
    <div class="readout">
      <span class="readout__label">Provider</span>
      <span class="readout__value">{{ num(providerRows.length) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">人格卡</span>
      <span class="readout__value">{{ num(personaRows.length) }}</span>
    </div>
    <div class="readout">
      <span class="readout__label">默认人格</span>
      <span class="readout__value" style="font-size: 15px">
        {{ binding.global_default || '未设置' }}
      </span>
    </div>
  </div>

  <div v-if="restartNeeded" class="warn-banner" role="status">
    已写入 {{ appliedFields.length }} 个字段。改动<strong>需要重启服务</strong>才生效——
    运行中的进程仍持有旧配置，Provider 冷却状态与流水线也不会热替换。
  </div>

  <section class="panel">
    <div class="panel__head">
      <h2>Provider 链路</h2>
      <span class="hint">按优先级排序，失败自动切换</span>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" :disabled="busy" @click="loadForEdit">
        {{ document ? '重新载入' : '载入以编辑' }}
      </button>
    </div>

    <div class="panel__body flush">
      <!-- read-only view when nothing has been loaded for editing -->
      <template v-if="!document">
        <table v-if="providerRows.length" class="data">
          <caption class="visually-hidden">Provider 链路</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">类型</th>
              <th scope="col">模型</th>
              <th scope="col">能力</th>
              <th scope="col" class="num">优先级</th>
              <th scope="col">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in providerRows" :key="row.id">
              <td class="key">{{ row.id }}</td>
              <td>{{ row.kind }}</td>
              <td>{{ row.model || '—' }}</td>
              <td>
                <span v-for="slot in row.slots" :key="slot" class="tag" style="margin-right: 4px">
                  {{ slot }}
                </span>
              </td>
              <td class="num">{{ row.priority }}</td>
              <td>
                <span class="tag" :class="row.enabled ? 'ok' : 'bad'">
                  {{ row.enabled ? '启用' : '停用' }}
                </span>
                <span v-if="statFor(row.id).failures" class="tag bad" style="margin-left: 4px">
                  失败 {{ statFor(row.id).failures }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">
          没有配置任何 Provider。点「载入以编辑」新增，或直接在
          <code>config/providers.yaml</code> 中添加后重启。
        </div>
      </template>

      <!-- editable view -->
      <div v-else class="edit">
        <p class="hint" style="margin: 0 0 8px">
          字面量密钥在读取时显示为掩码。保持 <code class="mono">{{ mask }}</code>
          不动表示沿用原值；清空则表示移除该密钥。
        </p>

        <table class="data">
          <caption class="visually-hidden">编辑 Provider</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">类型</th>
              <th scope="col">Base URL</th>
              <th scope="col">模型</th>
              <th scope="col">API Key</th>
              <th scope="col" class="num">优先级</th>
              <th scope="col">启用</th>
              <th scope="col"><span class="visually-hidden">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in drafts" :key="row.id" :class="{ 'edit__row--dirty': edited[row.id] }">
              <th scope="row">
                <input
                  v-model="row.id"
                  class="field"
                  style="min-width: 96px"
                  aria-label="Provider ID"
                  @input="markEdited(row.id)"
                />
              </th>
              <td>
                <input
                  v-model="row.kind"
                  class="field"
                  style="min-width: 120px"
                  aria-label="类型"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <input
                  v-model="row.base_url"
                  class="field"
                  style="min-width: 180px"
                  aria-label="Base URL"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <input
                  v-model="row.model"
                  class="field"
                  style="min-width: 120px"
                  aria-label="模型"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <!-- type="text" not "password": the value shown is already a mask or an
                     env: reference, and hiding it would stop the operator from seeing
                     which variable this provider is wired to. -->
                <input
                  class="field"
                  style="min-width: 140px"
                  :value="row.api_key"
                  aria-label="API Key"
                  spellcheck="false"
                  @input="onSecretInput(row, $event)"
                />
              </td>
              <td class="num">
                <input
                  v-model.number="row.priority"
                  class="field"
                  style="width: 64px; text-align: right"
                  type="number"
                  aria-label="优先级"
                  @input="markEdited(row.id)"
                />
              </td>
              <td>
                <input
                  v-model="row.enabled"
                  type="checkbox"
                  :aria-label="`启用 ${row.id}`"
                  @change="markEdited(row.id)"
                />
              </td>
              <td>
                <button class="btn ghost" type="button" @click="removeRow(index)">移除</button>
              </td>
            </tr>
          </tbody>
        </table>

        <div class="row" style="margin-top: 10px">
          <button class="btn ghost" type="button" @click="addRow">新增 Provider</button>
          <span class="strip__spacer" />
          <span class="hint">{{ hasEdits ? '有未提交的改动' : '无改动' }}</span>
          <button class="btn lamp" type="button" :disabled="busy || !hasEdits" @click="previewDiff">
            {{ busy ? '计算中…' : '查看将要写入的改动' }}
          </button>
        </div>

        <p v-if="loadError" class="error-banner" style="margin-top: 8px" role="alert">
          {{ loadError }}
        </p>
        <p v-if="flowError" class="error-banner" style="margin-top: 8px" role="alert">
          {{ flowError }}
        </p>
      </div>
    </div>
  </section>

  <section v-if="showDiff && diff" class="panel">
    <div class="panel__head">
      <h2>待写入的改动</h2>
      <span class="tag">{{ diff.changed_fields.length }} 个字段</span>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" @click="showDiff = false">取消</button>
      <button class="btn lamp" type="button" :disabled="busy || diff.empty" @click="requestApply">
        确认写入
      </button>
    </div>
    <div class="panel__body">
      <p class="warn-banner" style="margin: 0 0 10px">
        这一步还<strong>没有</strong>写盘。下面是即将写入
        <code class="mono">{{ document?.path }}</code> 的实际改动。
      </p>
      <DiffEditor :diff="diff.diff" filename="providers.yaml" />
      <div class="hint" style="margin-top: 8px">
        涉及字段：{{ diff.changed_fields.join('、') || '（无）' }}
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>人格卡</h2>
      <span class="hint">点击展开系统提示词预览 · 暂不支持面板内编辑</span>
    </div>
    <div class="panel__body flush">
      <div v-if="!personaRows.length" class="empty">
        <code>config/personas/</code> 下没有可加载的人格卡。
      </div>
      <div v-else class="scroll">
        <table class="data">
          <caption class="visually-hidden">人格卡</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">名称</th>
              <th scope="col">风格</th>
              <th scope="col">唤醒词</th>
              <th scope="col" class="num">字数上限</th>
              <th scope="col" class="num">温度</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in personaRows" :key="row.id">
              <tr style="cursor: pointer" @click="toggle(row.id)">
                <th scope="row">
                  {{ row.id }}
                  <span v-if="!row.enabled" class="tag bad" style="margin-left: 6px">停用</span>
                </th>
                <td>{{ row.name }}</td>
                <td>{{ row.style || '—' }}</td>
                <td>{{ row.wake_words.join(' / ') || '—' }}</td>
                <td class="num">{{ row.max_reply_chars || '默认' }}</td>
                <td class="num">{{ row.temperature ?? '默认' }}</td>
              </tr>
              <tr v-if="expanded === row.id">
                <td colspan="6" style="background: var(--surface-3)">
                  <div class="hint" style="margin-bottom: 6px">
                    系统提示词{{ row.system_prompt_truncated ? '（已截断）' : '' }}
                  </div>
                  <pre
                    style="
                      white-space: pre-wrap;
                      font-size: 12px;
                      line-height: 1.6;
                      margin: 0;
                      max-height: 320px;
                      overflow: auto;
                    "
                    >{{ row.system_prompt || '（空）' }}</pre
                  >
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel__head">
      <h2>人格绑定</h2>
      <span class="hint">未列出的群/用户使用默认人格</span>
    </div>
    <div class="panel__body">
      <div class="grid cols-2">
        <div>
          <div class="hint" style="margin-bottom: 6px">群绑定</div>
          <table v-if="Object.keys(binding.groups ?? {}).length" class="data">
            <caption class="visually-hidden">群绑定</caption>
            <thead>
              <tr>
                <th scope="col">群号</th>
                <th scope="col">人格</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(pid, gid) in binding.groups" :key="gid">
                <th scope="row">{{ gid }}</th>
                <td>{{ pid }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">没有群级别绑定。</div>
        </div>
        <div>
          <div class="hint" style="margin-bottom: 6px">用户绑定</div>
          <table v-if="Object.keys(binding.users ?? {}).length" class="data">
            <caption class="visually-hidden">用户绑定</caption>
            <thead>
              <tr>
                <th scope="col">用户</th>
                <th scope="col">人格</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(pid, uid) in binding.users" :key="uid">
                <th scope="row">{{ truncate(String(uid), 20) }}</th>
                <td>{{ pid }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">没有用户级别绑定。</div>
        </div>
      </div>
    </div>
  </section>

  <div v-if="providers.error.value" class="error-banner">{{ providers.error.value }}</div>
  <div v-if="personas.error.value" class="error-banner">{{ personas.error.value }}</div>

  <ConfirmDialog
    :open="confirmOpen"
    title="写入 Provider 配置"
    :detail="`将修改 ${diff?.changed_fields.length ?? 0} 个字段并写入 providers.yaml。改动需要重启服务才生效。`"
    confirm-label="写入"
    :busy="busy"
    @confirm="applyChanges"
    @cancel="confirmOpen = false"
  />
</template>

<style scoped>
.edit {
  padding: 12px;
}

.edit__row--dirty th,
.edit__row--dirty td {
  background: var(--warn-soft);
}
</style>
