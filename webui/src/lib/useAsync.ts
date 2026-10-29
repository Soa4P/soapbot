import { onMounted, ref, watch } from 'vue'

import { ApiError } from '@/api/client'
import { refreshTick } from '@/lib/refresh'

/**
 * Load-once-plus-on-refresh, with an error string a panel can render.
 *
 * Deliberately not a polling hook: every view here is a snapshot, and a 2-second poll
 * on six panels is six times the load for information nobody watches change. The
 * global refresh button is the update mechanism.
 */
export function useAsync<T>(loader: () => Promise<T>) {
  const data = ref<T | null>(null) as { value: T | null }
  const error = ref('')
  const loading = ref(false)

  async function reload(): Promise<void> {
    loading.value = true
    try {
      data.value = await loader()
      error.value = ''
    } catch (err) {
      error.value = err instanceof ApiError ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  onMounted(reload)
  watch(refreshTick, reload)

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
