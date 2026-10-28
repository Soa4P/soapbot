<script setup lang="ts">
import { computed } from 'vue'

/**
 * Renders a unified diff, line by line, with the original and new numbers.
 *
 * Why not a side-by-side editor
 * -----------------------------
 * This is a *confirmation* surface, not an editing surface. The edit already happened
 * in the form; what is shown here is the exact set of lines that will change on disk,
 * including the ones the form never displayed — a comment above the provider, a field
 * another admin touched. Side-by-side implies you can still change things here, and
 * every extra affordance on a confirmation step makes it easier to click through.
 *
 * Rendering the raw `difflib` output as a `<pre>` would be simpler and would defeat the
 * purpose: the whole value is that additions and removals are distinguishable at a
 * glance, including for someone who cannot distinguish red from green — hence the
 * explicit `+`/`-` gutter and the text labels, not colour alone.
 */
const props = defineProps<{
  diff: string
  filename?: string
}>()

interface Line {
  kind: 'add' | 'del' | 'ctx' | 'meta'
  text: string
  oldNo: number | null
  newNo: number | null
}

const lines = computed<Line[]>(() => {
  const out: Line[] = []
  let oldNo = 0
  let newNo = 0

  for (const raw of props.diff.split('\n')) {
    if (raw.startsWith('--- ') || raw.startsWith('+++ ') || raw.startsWith('@@')) {
      out.push({ kind: 'meta', text: raw, oldNo: null, newNo: null })
      // `@@ -3,4 +3,5 @@` — start counting from the stated line numbers so the gutter
      // matches the real file rather than the position in this snippet.
      const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(raw)
      if (hunk) {
        oldNo = Number(hunk[1]) - 1
        newNo = Number(hunk[2]) - 1
      }
      continue
    }
    if (raw === '') continue

    const marker = raw[0]
    const text = raw.slice(1)
    if (marker === '+') {
      newNo += 1
      out.push({ kind: 'add', text, oldNo: null, newNo })
    } else if (marker === '-') {
      oldNo += 1
      out.push({ kind: 'del', text, oldNo, newNo: null })
    } else {
      oldNo += 1
      newNo += 1
      out.push({ kind: 'ctx', text, oldNo, newNo })
    }
  }
  return out
})

const counts = computed(() => ({
  added: lines.value.filter((l) => l.kind === 'add').length,
  removed: lines.value.filter((l) => l.kind === 'del').length,
}))
</script>

<template>
  <div class="diff">
    <div class="diff__head">
      <span class="mono">{{ filename ?? '配置文件' }}</span>
      <span class="tag ok">+{{ counts.added }}</span>
      <span class="tag bad">−{{ counts.removed }}</span>
    </div>

    <p v-if="!lines.length" class="empty">没有改动。</p>

    <div v-else class="diff__body" role="table" aria-label="待写入的改动">
      <div v-for="(line, index) in lines" :key="index" class="diff__line" :class="`diff__line--${line.kind}`" role="row">
        <span class="diff__no mono" role="cell">{{ line.oldNo ?? '' }}</span>
        <span class="diff__no mono" role="cell">{{ line.newNo ?? '' }}</span>
        <span class="diff__sign mono" role="cell" aria-hidden="true">
          {{ line.kind === 'add' ? '+' : line.kind === 'del' ? '−' : '' }}
        </span>
        <span class="diff__text mono" role="cell">{{ line.text }}</span>
        <span class="visually-hidden">
          {{ line.kind === 'add' ? '新增行' : line.kind === 'del' ? '删除行' : '' }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.diff {
  display: grid;
  gap: 6px;
}

.diff__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--ink-2);
}

.diff__body {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: auto;
  max-height: 400px;
  background: var(--surface);
  font-size: 11.5px;
}

.diff__line {
  display: grid;
  grid-template-columns: 38px 38px 16px minmax(0, 1fr);
  gap: 0;
  align-items: baseline;
  white-space: pre;
}

.diff__line--meta {
  grid-template-columns: minmax(0, 1fr);
  background: var(--surface-3);
  color: var(--ink-3);
  padding: 3px 8px;
  font-size: 10.5px;
}

.diff__no {
  color: var(--ink-3);
  font-size: 10px;
  text-align: right;
  padding: 2px 6px;
  user-select: none;
  border-right: 1px solid var(--border);
}

.diff__sign {
  text-align: center;
  padding: 0 2px;
  font-weight: 600;
}

.diff__text {
  padding: 2px 8px;
  color: var(--ink);
  overflow-x: auto;
}

.diff__line--add {
  background: var(--ok-soft);
}

.diff__line--add .diff__sign {
  color: var(--ok);
}

.diff__line--del {
  background: var(--danger-soft);
}

.diff__line--del .diff__sign {
  color: var(--danger);
}

.diff__line--ctx .diff__text {
  color: var(--ink-2);
}
</style>
