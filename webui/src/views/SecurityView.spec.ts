/**
 * "Revoke all tokens" is the button an operator presses when a device is lost.
 *
 * Two things have to be true afterwards, and both were false (S-FE-03):
 *
 * 1. The panel says what actually happened. It used to claim a replacement session token
 *    had been issued — that stopped being true when the closure redesign made revocation
 *    terminal, so the operator believed they were still signed in while every request
 *    was being refused.
 * 2. The way back in is visible. The server mints a single-use bootstrap credential in
 *    the same response, and the old code threw it away: recovering meant opening a shell
 *    on the server, which is the round trip the panel exists to avoid.
 *
 * A third property is a non-action: the view must not call `auth.refresh()` on success.
 * Refreshing flips the shell to the login dialog, unmounts this page, and takes the
 * credential with it.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  audit: vi.fn(async () => ({ events: [], counts: {}, truncated: false })),
  access: vi.fn(async () => ({ owner_ids: [], admin_ids: [], member_ids: [] })),
  integrity: vi.fn(async () => ({ ok: true, checks: [] })),
  screenOps: vi.fn(async () => ({ ops: [] })),
  screenStatus: vi.fn(async () => ({ killed: false, hold_until: 0 })),
  revocations: vi.fn(async () => ({ revoked_before: 0, count: 0, tokens: [] })),
  revokeAllTokens: vi.fn(async () => ({
    ok: true,
    revoked_before: 1700000000,
    bootstrap_token: 'BOOTSTRAP-AFTER-REVOKE',
    requires_login: true,
  })),
}))

const auth = vi.hoisted(() => ({ refresh: vi.fn(async () => undefined) }))

vi.mock('@/api/client', () => ({ api }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    refresh: auth.refresh,
    canEditAuthority: false,
    role: 'owner',
  }),
}))

import SecurityView from './SecurityView.vue'

function mountView() {
  return mount(SecurityView, {
    attachTo: document.body,
    // The view links to other pages; a router is not what this test is about.
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

function revokeButton(wrapper: ReturnType<typeof mountView>) {
  // The suite renders in English; a CJK literal here would also fail the
  // "no hardcoded strings in scripts" gate that keeps the UI translatable.
  const found = wrapper.findAll('button').find((b) => b.text().includes('Revoke all'))
  if (!found) throw new Error('revoke-all button not rendered')
  return found
}

describe('SecurityView token revocation', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockClear()
    auth.refresh.mockClear()
  })

  it('shows the bootstrap credential the server minted', async () => {
    const wrapper = mountView()
    await flushPromises()

    await revokeButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('BOOTSTRAP-AFTER-REVOKE')
    // …and says it will not be shown again, so nobody closes the page expecting to
    // find it later.
    expect(wrapper.text()).toContain('Shown once')
  })

  it('does not refresh the session and hide the credential', async () => {
    const wrapper = mountView()
    await flushPromises()

    await revokeButton(wrapper).trigger('click')
    await flushPromises()

    expect(auth.refresh).not.toHaveBeenCalled()
  })

  it('clears the previous credential when the action is run again', async () => {
    api.revokeAllTokens.mockResolvedValueOnce({
      ok: true,
      revoked_before: 1,
      bootstrap_token: 'FIRST',
      requires_login: true,
    })
    const wrapper = mountView()
    await flushPromises()
    await revokeButton(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('FIRST')

    await revokeButton(wrapper).trigger('click')
    await flushPromises()
    // Second run returns the default token; the stale one must be gone, or the operator
    // copies a credential that has already been replaced.
    expect(wrapper.text()).not.toContain('FIRST')
    expect(wrapper.text()).toContain('BOOTSTRAP-AFTER-REVOKE')
  })
})
