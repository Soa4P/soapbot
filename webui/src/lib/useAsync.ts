import { onMounted, ref, watch } from 'vue'

import { ApiError } from '@/api/client'
import { refreshTick } from '@/lib/refresh'

/**
 * Load-once-plus-on-refresh, with an error string a panel can render.
 *
 * Deliberately not a polling hook: every view here is a snapshot, and a 2-second poll
 * on six panels is six times the load for information nobody watches change. The
 * global refresh button is the update mechanism.
 *
 * A short-lived module-level cache makes switching pages instant. Every view used to
 * re-fetch on mount with nothing shown in between, so 01→09 and back always cost two
 * round trips and two blank frames. Cached data is painted immediately and refreshed
 * in the background, so the page is never both stale *and* empty.
 */
const CACHE_TTL_MS = 15_000
const cache = new Map<string, { at: number; data: unknown }>()

/** Drop everything; used by the global refresh button, which means "really reload". */
export function clearAsyncCache(): void {
  cache.clear()
}

export function useAsync<T>(loader: () => Promise<T>, cacheKey?: string) {
  const data = ref<T | null>(null) as { value: T | null }
  const error = ref('')
  const loading = ref(false)

  async function reload(): Promise<void> {
    loading.value = true
    try {
      data.value = await loader()
      error.value = ''
      if (cacheKey) cache.set(cacheKey, { at: Date.now(), data: data.value })
    } catch (err) {
      error.value = err instanceof ApiError ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    const hit = cacheKey ? cache.get(cacheKey) : undefined
    if (hit && Date.now() - hit.at < CACHE_TTL_MS) {
      // Show what we have, then confirm it. Marking ``loading`` while content is
      // already visible would reintroduce the skeleton on every page switch.
      data.value = hit.data as T
      void reload()
      return
    }
    void reload()
  })

  watch(refreshTick, () => {
    cache.clear()
    void reload()
  })

  return { data, error, loading, reload }
}

/**
 * Treat a 503 from an optional subsystem as a state, not a failure.
 *
 * Matches the raw detail the backend sends, which is deliberately English: internal
 * error text is not a translated surface (see the backend catalogue's note). The old
 * Chinese alternative here was a leftover from before that rule, and matched nothing.
 */
export function isUnavailable(err: string): boolean {
  return err.includes('not initialised')
}
