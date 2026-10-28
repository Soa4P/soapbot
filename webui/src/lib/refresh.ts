import { ref } from 'vue'

/**
 * One global refresh signal.
 *
 * Every page here is a read-only snapshot; there is nothing to push, and a websocket
 * would add a second connection to keep alive for a panel an operator opens for two
 * minutes. A button that bumps a counter and a `watch` in each view is the whole
 * mechanism, and it behaves identically for all six pages.
 */
export const refreshTick = ref(0)

export function bumpRefresh(): void {
  refreshTick.value += 1
}
