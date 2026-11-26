/**
 * The confirmation dialog guards destructive writes, so the two things that make it a
 * *dialog* — focus never leaving it, and Esc cancelling — have to actually run.
 *
 * Both were dead: `isOpen` was assigned `props.open` once during setup, when every
 * caller mounts it closed, so the focus trap never armed and Esc never reached the
 * cancel path. The markup looked right, which is why nobody noticed (S-FE-05).
 *
 * The tests drive the prop, not the component's internals: open it, press Tab or Esc,
 * and assert on what happens to focus and to the emitted events.
 */
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import ConfirmDialog from './ConfirmDialog.vue'

const mounted: Array<{ unmount: () => void }> = []

// jsdom does no layout, so `offsetParent` is null for every element and the trap's
// visibility filter (`el.offsetParent !== null`) would discard the very buttons it is
// supposed to focus. Reporting the body as the offset parent is the minimum lie that
// makes layout-dependent code testable — the filter still exists for real browsers,
// where a `display:none` button must not be focused.
let restoreOffsetParent: (() => void) | null = null

beforeEach(() => {
  const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetParent')
  Object.defineProperty(HTMLElement.prototype, 'offsetParent', {
    configurable: true,
    get() {
      return document.body
    },
  })
  restoreOffsetParent = () => {
    if (original) Object.defineProperty(HTMLElement.prototype, 'offsetParent', original)
    else delete (HTMLElement.prototype as { offsetParent?: unknown }).offsetParent
  }
})

function mountDialog(open = false) {
  const wrapper = mount(ConfirmDialog, {
    props: { open, title: 't', detail: 'd' },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  return wrapper
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  document.body.innerHTML = ''
  restoreOffsetParent?.()
  restoreOffsetParent = null
})

describe('ConfirmDialog keyboard behaviour', () => {
  it('traps focus once the prop opens it', async () => {
    const wrapper = mountDialog(false)
    await wrapper.setProps({ open: true })
    // Focus lands on the first focusable control (cancel) after a paint frame.
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))

    const panel = document.querySelector('[role="alertdialog"]')
    expect(panel).not.toBeNull()
    expect(panel?.contains(document.activeElement)).toBe(true)
  })

  it('emits cancel on Escape', async () => {
    const wrapper = mountDialog(false)
    await wrapper.setProps({ open: true })
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('stops listening once closed again', async () => {
    const wrapper = mountDialog(true)
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
    await wrapper.setProps({ open: false })

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(wrapper.emitted('cancel')).toBeUndefined()
  })
})
