<script setup lang="ts">
/**
 * 记忆星图（xingxi 改编，soapbot 形态）：已提炼记忆的散点星图。
 *
 * 与原仓库的差别：原版是独立站点的力导向图（elkjs + d3），数据来自课程树；
 * 这里是面板内嵌组件，数据来自既有的 /api/memory/items——x = 时间（created_at），
 * y = 重要度，点径 = 重要度，色 = 记忆层。零依赖（原生 SVG），hover 显示内容，
 * 点击发出 select 事件让外层过滤 scope。纯前端渲染，不新增端点。
 */
import { computed, ref } from 'vue'

import { t } from '@/i18n'

const props = defineProps<{
  rows: Array<{
    id: number
    layer: string
    scope: string
    content: string
    importance: number
    created_at: number
  }>
}>()

const emit = defineEmits<{ select: [scope: string] }>()

const W = 900
const H = 320
const PAD = { left: 46, right: 20, top: 16, bottom: 28 }

const selectedScope = ref('')

const LAYER_COLORS: Record<string, string> = {
  'MemoryLayer.SEMANTIC': '#7dd3fc',
  semantic: '#7dd3fc',
  'MemoryLayer.EPISODIC': '#fbbf24',
  episodic: '#fbbf24',
  'MemoryLayer.WORKING': '#a78bfa',
  working: '#a78bfa',
}

function layerColor(layer: string): string {
  return LAYER_COLORS[layer] ?? '#94a3b8'
}

/** x 轴：时间从旧到新。全部行共享同一个 min/max，画布内均匀映射。 */
const points = computed(() => {
  const rows = props.rows
  if (!rows.length) return []
  const times = rows.map((r) => r.created_at || 0)
  const tMin = Math.min(...times)
  const tMax = Math.max(...times)
  const span = Math.max(1, tMax - tMin)
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  return rows.map((row) => {
    const t = row.created_at || 0
    const importance = Math.max(0, Math.min(1, Number(row.importance) || 0))
    return {
      id: row.id,
      scope: row.scope,
      content: row.content,
      layer: row.layer,
      importance,
      x: PAD.left + ((t - tMin) / span) * innerW,
      y: PAD.top + (1 - importance) * innerH,
      r: 3 + importance * 5,
      color: layerColor(row.layer),
      when: tMin === tMax ? '' : new Date(t * 1000).toLocaleDateString(),
    }
  })
})

const ticks = computed(() => {
  const rows = props.rows
  if (!rows.length) return []
  const times = rows.map((r) => r.created_at || 0)
  const tMin = Math.min(...times)
  const tMax = Math.max(...times)
  const span = Math.max(1, tMax - tMin)
  const innerW = W - PAD.left - PAD.right
  const count = 4
  return Array.from({ length: count + 1 }, (_, i) => ({
    x: PAD.left + (i / count) * innerW,
    label: new Date((tMin + (i / count) * span) * 1000).toLocaleDateString(),
  }))
})

function pick(row: (typeof points.value)[number]): void {
  selectedScope.value = row.scope
  emit('select', row.scope)
}
</script>

<template>
  <div class="starmap">
    <div v-if="!points.length" class="starmap__empty">{{ t('memory.starmap.empty') }}</div>
    <svg
      v-else
      class="starmap__svg"
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-label="t('memory.starmap.aria')"
      @click="selectedScope = ''"
    >
      <!-- 重要度参考线：顶=1，底=0 -->
      <line
        v-for="i in [0, 1]"
        :key="`grid-${i}`"
        :x1="PAD.left"
        :x2="W - PAD.right"
        :y1="PAD.top + i * (H - PAD.top - PAD.bottom)"
        :y2="PAD.top + i * (H - PAD.top - PAD.bottom)"
        class="starmap__grid"
      />
      <text
        :x="PAD.left - 6"
        :y="PAD.top + 4"
        class="starmap__axis"
        text-anchor="end"
      >
        {{ t('memory.starmap.high') }}
      </text>
      <text
        :x="PAD.left - 6"
        :y="H - PAD.bottom"
        class="starmap__axis"
        text-anchor="end"
      >
        {{ t('memory.starmap.low') }}
      </text>
      <text
        v-for="(tick, i) in ticks"
        :key="`tick-${i}`"
        :x="tick.x"
        :y="H - PAD.bottom + 16"
        class="starmap__axis"
        text-anchor="middle"
      >
        {{ tick.label }}
      </text>
      <circle
        v-for="p in points"
        :key="p.id"
        :cx="p.x"
        :cy="p.y"
        :r="p.r"
        :fill="p.color"
        :class="{ 'starmap__star--selected': selectedScope && p.scope === selectedScope }"
        class="starmap__star"
        :tabindex="0"
        role="button"
        :aria-label="p.content.slice(0, 80)"
        @click.stop="pick(p)"
        @keydown.enter.prevent="pick(p)"
      />
    </svg>
    <p v-if="selectedScope" class="starmap__hint">
      {{ t('memory.starmap.filtered', { scope: selectedScope }) }}
      <button class="btn ghost" type="button" @click="selectedScope = ''">
        {{ t('memory.starmap.clear') }}
      </button>
    </p>
    <p class="starmap__legend hint">
      <span class="starmap__dot" style="background: #7dd3fc" /> semantic
      <span class="starmap__dot" style="background: #fbbf24; margin-left: 10px" /> episodic
      <span class="starmap__dot" style="background: #a78bfa; margin-left: 10px" /> working
      <span style="margin-left: 10px">{{ t('memory.starmap.legendNote') }}</span>
    </p>
  </div>
</template>

<style scoped>
.starmap__svg {
  width: 100%;
  height: auto;
  background: var(--surface-2, #0b1020);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.starmap__empty {
  padding: 24px;
  text-align: center;
  color: var(--ink-3);
}

.starmap__grid {
  stroke: var(--border);
  stroke-dasharray: 4 4;
}

.starmap__axis {
  font-size: 10px;
  fill: var(--ink-3);
}

.starmap__star {
  cursor: pointer;
  opacity: 0.85;
  outline: none;
}

.starmap__star:hover,
.starmap__star:focus-visible,
.starmap__star--selected {
  opacity: 1;
  stroke: #fff;
  stroke-width: 1.5;
}

.starmap__hint {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 0;
  color: var(--ink-2);
}

.starmap__legend {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
}

.starmap__dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
</style>
