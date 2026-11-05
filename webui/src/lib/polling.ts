import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Interval refresh that gets out of the way.
 *
 * The panel used to `setInterval(load, 4000)` and replace the whole array on every
 * tick. Three things went wrong at once: the list was rebuilt under the cursor while
 * someone was reading it, the page kept polling in a background tab (and in every tab
 * at once), and each tick re-rendered even when nothing had changed.
 *
 * This keeps the timer but skips a tick when refreshing would be disruptive:
 *  - the tab is hidden (nobody is looking; a background tab polling is pure load),
 *  - the person is scrolling (the list would jump under their finger),
 *  - focus is in a field (a re-render can drop the caret).
 *
 * ``paused`` is exposed so the page can say *why* the numbers are standing still
 * instead of looking frozen.
 */
/** Set while a scroll is in progress, cleared shortly after it stops. */
let scrolling = false
let scrollIdleTimer: number | undefined

function onAnyScroll(): void {
  scrolling = true
  if (scrollIdleTimer) window.clearTimeout(scrollIdleTimer)
  // A short grace period, not the whole scroll: the list should resume soon after the
  // person stops looking at a fixed spot, not only when they leave the page.
  scrollIdleTimer = window.setTimeout(() => {
    scrolling = false
  }, 1200)
}

/**
 * Whether refreshing right now would be disruptive.
 *
 * Exported because two pages keep their own timer (a manual "follow" toggle on the trace
 * list, and the QR-code poll that has to stay at 3s). They need the same rule, and a
 * second copy of it would drift.
 */
export function refreshWouldDisrupt(): boolean {
  if (typeof document === 'undefined') return false
  if (document.visibilityState === 'hidden') return true
  if (scrolling) return true
  const active = document.activeElement
  if (!active) return false
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName)
}

export function usePolling(run: () => void | Promise<void>, intervalMs: number) {
  const paused = ref(false)
  /** When the last successful tick actually ran; 0 until the first one. */
  const lastRunAt = ref(0)
  let timer: number | undefined

  function busy(): boolean {
    return refreshWouldDisrupt()
  }

  function tick(): void {
    if (busy()) {
      paused.value = true
      return
    }
    paused.value = false
    lastRunAt.value = Date.now()
    void run()
  }

  onMounted(() => {
    timer = window.setInterval(tick, intervalMs)
    window.addEventListener('scroll', onAnyScroll, { passive: true, capture: true })
  })

  onBeforeUnmount(() => {
    if (timer) window.clearInterval(timer)
    window.removeEventListener('scroll', onAnyScroll, { capture: true })
  })

  return { paused, lastRunAt }
}

/**
 * A clock that ticks, so "updated 12s ago" actually counts up.
 *
 * `Date.now()` inside a computed is not reactive: the value is computed once and then
 * frozen, which produces a timestamp that says "3s ago" forever. One shared timer per
 * page is cheaper than one per label, and it stops with the component.
 */
export function useNow(intervalMs = 1000) {
  const now = ref(Date.now())
  let timer: number | undefined

  onMounted(() => {
    timer = window.setInterval(() => {
      now.value = Date.now()
    }, intervalMs)
  })

  onBeforeUnmount(() => {
    if (timer) window.clearInterval(timer)
  })

  return now
}
