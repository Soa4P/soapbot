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

/** Treat a 503 from an optional subsystem as a state, not a failure. */
export function isUnavailable(err: string): boolean {
  return err.includes('not initialised') || err.includes('未初始化')
}
