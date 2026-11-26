<script setup lang="ts">
import { computed, inject, type Ref } from 'vue'

import { t } from '@/i18n'
import { QQ_MENU_KEY, type MenuNode, nodeAt, removeAt } from '@/lib/qqMenu'

/**
 * One node of the QQ menu tree.
 *
 * The tree itself lives in the injected reactive array, not in props: a props-passing
 * editor either mutates a prop (which Vue forbids, and for good reason — the parent
 * cannot see it) or needs an emit-up-the-tree dance per keystroke. A shared array with a
 * numeric path keeps the "who owns the data" answer obvious: the editor does.
 *
 * Recursive by name, because the validator allows three levels and flattening them would
 * hide the nesting that makes a menu a menu.
 */
const props = defineProps<{
  path: number[]
  depth: number
  maxDepth: number
}>()

const injected = inject(QQ_MENU_KEY)
if (!injected) throw new Error('QqMenuItem requires the menu array from QqMenuEditor')
// Bound to a const with a narrowed type: `inject` returns `T | undefined` and the throw
// above is not enough for the type checker inside the computed below.
const menu: Ref<MenuNode[]> = injected

const item = computed<MenuNode>(() => nodeAt(menu.value, props.path))
const isMenu = computed(() => item.value.type === 'menu')
const canNest = computed(() => props.depth < props.maxDepth)

function addChild(): void {
  if (!item.value.children) item.value.children = []
  item.value.children.push({ name: '', type: 'send', reply: '' })
}

function removeChild(index: number): void {
  item.value.children?.splice(index, 1)
}

function removeSelf(): void {
  removeAt(menu.value, props.path)
}
</script>

<template>
  <div class="qq-item" :data-depth="depth">
    <div class="row">
      <input
        v-model="item.name"
        class="field"
        style="min-width: 120px"
        :placeholder="t('qqMenu.namePlaceholder')"
        :aria-label="t('qqMenu.name')"
      />
      <select v-model="item.type" class="field" :aria-label="t('qqMenu.type')">
        <option value="send">{{ t('qqMenu.typeSend') }}</option>
        <option value="link">{{ t('qqMenu.typeLink') }}</option>
        <option value="menu">{{ t('qqMenu.typeMenu') }}</option>
      </select>
      <input
        v-if="item.type === 'send'"
        v-model="item.reply"
        class="field"
        style="min-width: 200px"
        :placeholder="t('qqMenu.replyPlaceholder')"
        :aria-label="t('qqMenu.reply')"
      />
      <input
        v-if="item.type === 'link'"
        v-model="item.url"
        class="field"
        style="min-width: 200px"
        placeholder="https://"
        :aria-label="t('qqMenu.url')"
      />
      <span v-if="isMenu" class="hint">{{ t('qqMenu.hasChildren') }}</span>
      <span class="strip__spacer" />
      <button v-if="isMenu && canNest" class="btn ghost" type="button" @click="addChild">
        {{ t('qqMenu.addChild') }}
      </button>
      <button class="btn ghost" type="button" @click="removeSelf">
        {{ t('common.delete') }}
      </button>
    </div>

    <!-- `menu` items carry their children; the validator rejects a menu with none. -->
    <div v-if="isMenu && item.children?.length" class="qq-item__children">
      <QqMenuItem
        v-for="(_child, index) in item.children"
        :key="index"
        :path="[...path, index]"
        :depth="depth + 1"
        :max-depth="maxDepth"
        @remove="removeChild(index)"
      />
    </div>
  </div>
</template>

<style scoped>
.qq-item {
  padding: 4px 0;
}
.qq-item__children {
  margin-left: 20px;
  border-left: 2px solid var(--border);
  padding-left: 10px;
}
</style>
