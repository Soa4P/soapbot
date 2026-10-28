import { onBeforeUnmount, watch, type Ref } from 'vue'

/**
 * Keeps keyboard focus inside a dialog, and gives it back when the dialog closes.
 *
 * Extracted because two dialogs need identical behaviour and both are easy to get
 * subtly wrong in isolation: the login dialog is the first thing an operator sees,
 * and the confirmation dialog guards destructive writes. A shared helper means the
 * Esc handling and the focus-restore target cannot drift apart between them.
 *
 * What it does *not* do: manage `aria-modal`, render a backdrop, or lock scrolling.
 * Those belong to the component's template — a composable that also injected DOM
 * would need to know about layout, which is exactly the coupling that makes these
 * helpers unmaintainable.
 */
const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function focusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  )
}

export interface FocusTrapOptions {
  /** Called on Esc. The dialog decides whether closing is allowed (e.g. not mid-write). */
  onEscape?: () => void
  /** Focus this element on open instead of the first focusable one. */
  initialFocus?: Ref<HTMLElement | null>
}

export function useFocusTrap(
  container: Ref<HTMLElement | null>,
  active: Ref<boolean>,
  options: FocusTrapOptions = {},
) {
  // The element that had focus before the dialog opened. Restoring it is not a
  // nicety: without it, closing a modal dumps focus on <body> and the next Tab
  // starts from the top of the page instead of where the operator was.
  let restoreTo: HTMLElement | null = null

  function onKeydown(event: KeyboardEvent) {
    if (!active.value) return
    if (event.key === 'Escape') {
      event.stopPropagation()
      options.onEscape?.()
      return
    }
    if (event.key !== 'Tab') return

    const root = container.value
    if (!root) return

    const items = focusable(root)
    if (!items.length) {
      // Nothing to focus: keep the trap closed rather than letting Tab escape.
      event.preventDefault()
      return
    }

    const first = items[0]
    const last = items[items.length - 1]
    const current = document.activeElement as HTMLElement | null

    if (!event.shiftKey && current === last) {
      event.preventDefault()
      first.focus()
    } else if (event.shiftKey && (current === first || !root.contains(current))) {
      event.preventDefault()
      last.focus()
    }
  }

  function activate() {
    restoreTo = document.activeElement as HTMLElement | null
    document.addEventListener('keydown', onKeydown, true)
    // Focus after paint: the element does not exist until Vue has rendered it.
    requestAnimationFrame(() => {
      const root = container.value
      if (!root) return
      const target = options.initialFocus?.value ?? focusable(root)[0] ?? root
      target.focus()
    })
  }

  function deactivate() {
    document.removeEventListener('keydown', onKeydown, true)
    if (restoreTo && document.contains(restoreTo)) {
      restoreTo.focus()
    }
    restoreTo = null
  }

  watch(active, (open) => (open ? activate() : deactivate()), { immediate: true })

  onBeforeUnmount(() => {
    document.removeEventListener('keydown', onKeydown, true)
  })

  return { activate, deactivate }
}
