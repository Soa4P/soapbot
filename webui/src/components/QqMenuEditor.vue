<script setup lang="ts">
import { onMounted, provide, ref } from 'vue'

import { api } from '@/api/client'
import QqMenuItem from '@/components/QqMenuItem.vue'
import { t } from '@/i18n'
import { QQ_MENU_KEY, type MenuNode } from '@/lib/qqMenu'

/**
 * QQ official bot menu editor — local document only.
 *
 * Uploading a menu needs an AppID/Secret this deployment does not have, so nothing here
 * calls the platform. What it does do is authoring and checking: the same validator a
 * future upload would use runs on every save, and the server answers with *all* the
 * problems at once. The panel says "本地骨架" on purpose — an operator who edits a menu
 * and expects it live on QQ would otherwise be misled by a green save.
 */
const MAX_DEPTH = 3

// Injected into QqMenuItem so the recursive editor can mutate one tree it owns; see
// lib/qqMenu.ts for why this is not props.
const items = ref<MenuNode[]>([])
provide(QQ_MENU_KEY, items)

const problems = ref<string[]>([])
const note = ref('')
const busy = ref(false)
const loaded = ref(false)

async function load(): Promise<void> {
  busy.value = true
  problems.value = []
  try {
    const body = await api.qqMenu()
    // Deep copy: the editor mutates in place, and a rejected save must not leave the
    // form showing edits that were never written.
    items.value = JSON.parse(JSON.stringify(body.document?.items ?? []))
    loaded.value = true
  } catch (err) {
    problems.value = [(err as Error).message]
  } finally {
    busy.value = false
  }
}

function addTop(): void {
  items.value.push({ name: '', type: 'send', reply: '' })
}

async function save(): Promise<void> {
  busy.value = true
  problems.value = []
  note.value = ''
  try {
    const body = await api.qqMenuSave({ items: JSON.parse(JSON.stringify(items.value)) })
    items.value = JSON.parse(JSON.stringify(body.document?.items ?? []))
    note.value = t('qqMenu.saved', { path: body.path })
  } catch (err) {
    // The server sends `detail.problems` for validation failures; anything else is a
    // transport error and is shown as-is.
    const payload = (err as any)?.detail
    const list = payload?.problems
    problems.value = Array.isArray(list) && list.length ? list : [(err as Error).message]
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="panel">
    <div class="panel__head">
      <h2>{{ t('qqMenu.title') }}</h2>
      <span class="hint">{{ t('qqMenu.localOnly') }}</span>
      <span class="strip__spacer" />
      <button class="btn ghost" type="button" :disabled="busy" @click="load">
        {{ t('config.reload') }}
      </button>
      <button class="btn ghost" type="button" :disabled="busy" @click="addTop">
        {{ t('qqMenu.addTop') }}
      </button>
      <button class="btn lamp" type="button" :disabled="busy || !loaded" @click="save">
        {{ busy ? t('config.saving') : t('qqMenu.save') }}
      </button>
    </div>
    <div class="panel__body">
      <p class="hint" style="margin: 0 0 8px">{{ t('qqMenu.limits') }}</p>

      <div v-if="!items.length" class="empty">{{ t('qqMenu.empty') }}</div>
      <div v-else class="stack">
        <QqMenuItem
          v-for="(_item, index) in items"
          :key="index"
          :path="[index]"
          :depth="1"
          :max-depth="MAX_DEPTH"
        />
      </div>

      <ul v-if="problems.length" class="error-banner" role="alert" style="margin-top: 10px">
        <li v-for="problem in problems" :key="problem">{{ problem }}</li>
      </ul>
      <p v-if="note" class="hint" role="status" style="margin-top: 8px">{{ note }}</p>
    </div>
  </section>
</template>
