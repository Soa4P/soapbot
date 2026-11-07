import { onMounted, onUnmounted, ref, watch } from 'vue'

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

  /**
   * Which request this hook is currently waiting for.
   *
   * Without it, two overlapping reloads settle in whatever order the network returns
   * them, and the slower one wins — so pressing the global refresh while a slow page load
   * is in flight can leave the panel showing the *older* snapshot with no error to
   * explain it. The same race makes a failed request overwrite a successful one, which
   * is how a page ends up displaying data and an error banner at the same time.
   *
   * A counter rather than ``AbortController``: the request has already been sent and the
   * server has already done the work, so cancelling saves nothing here. What has to be
   * prevented is the late result being *applied*, and comparing an integer does that in
   * one line with no cleanup to forget.
   */
  let seq = 0
  let disposed = false

  onUnmounted(() => {
    // Invalidates any request still in flight. Without this, navigating away while a
    // slow read is pending writes into refs of a destroyed component and into the
    // module cache, where a later view can pick up data from a page it never opened.
    disposed = true
    seq += 1
  })

  async function reload(): Promise<void> {
    if (disposed) return
    const mine = ++seq
    loading.value = true
    // A previous failure must not stay on screen while its replacement is loading;
    // the result of the new request is the only thing that can clear it otherwise.
    error.value = ''
    try {
      const result = await loader()
      if (disposed || mine !== seq) return
      data.value = result
      if (cacheKey) cache.set(cacheKey, { at: Date.now(), data: result })
    } catch (err) {
      // The failure path needs the same guard as the success path. A stale rejection
      // overwriting a fresh success is the worse of the two bugs: the page shows correct
      // data with a red banner, and the operator reports the data as wrong.
      if (disposed || mine !== seq) return
      error.value = err instanceof ApiError ? err.message : String(err)
    } finally {
      // Only the newest request may clear the spinner; an older one finishing first
      // would hide the fact that a request is still outstanding.
      if (!disposed && mine === seq) loading.value = false
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
