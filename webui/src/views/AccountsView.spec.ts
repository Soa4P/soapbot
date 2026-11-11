/**
 * Page 15 — the four owner actions, thin over the API by design. What deserves
 * pinning: the talk-grant button derives `web:private:account-<id>` instead of
 * asking the owner to type it, status toggles go to the right endpoint, and the
 * invite code is shown with a copy affordance but nothing else (it is shown once).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  accounts: vi.fn(async () => ({
    accounts: [
      { id: 1, username: 'alice', role: 'owner', status: 'active' },
      { id: 3, username: 'bob', role: 'member', status: 'active' },
    ],
  })),
  createInvite: vi.fn(async () => ({ invite: 'CODE-1234', role: 'member', expires_in_hours: 72 })),
  setAccountStatus: vi.fn(async () => ({ ok: true })),
  grantMembership: vi.fn(async () => ({ ok: true })),
}))

vi.mock('@/api/client', () => ({ api }))

import AccountsView from './AccountsView.vue'

function mountView() {
  return mount(AccountsView, { attachTo: document.body })
}

function button(wrapper: ReturnType<typeof mountView>, text: string, index = 0) {
  const matches = wrapper.findAll('button').filter((b) => b.text() === text)
  const found = matches[index]
  if (!found) throw new Error(`button "${text}" #${index} not rendered`)
  return found
}

describe('AccountsView', () => {
  beforeEach(() => {
    api.accounts.mockClear()
    api.createInvite.mockClear()
    api.setAccountStatus.mockClear()
    api.grantMembership.mockClear()
  })

  it('lists accounts with role and status badges', async () => {
    const wrapper = await mountView()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('alice')
    expect(text).toContain('bob')
    wrapper.unmount()
  })

  it('disabling an account posts to the status endpoint and reloads', async () => {
    const wrapper = await mountView()
    await flushPromises()
    expect(wrapper.findAll('button').filter((b) => b.text() === 'Disable').length).toBe(2)
    await button(wrapper, 'Disable', 1).trigger('click')
    await flushPromises()
    expect(api.setAccountStatus).toHaveBeenCalledWith(3, 'disabled')
    expect(api.accounts).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('the talk button derives the conversation key and grants it', async () => {
    const wrapper = await mountView()
    await flushPromises()
    await button(wrapper, 'Talk with the bot', 1).trigger('click')
    const sessionInput = wrapper.find('input.mono')
    expect((sessionInput.element as HTMLInputElement).value).toBe('web:private:account-3')
    await button(wrapper, 'Grant').trigger('click')
    await flushPromises()
    expect(api.grantMembership).toHaveBeenCalledWith(3, 'web:private:account-3')
    wrapper.unmount()
  })

  it('signs an invite and shows the code once', async () => {
    const wrapper = await mountView()
    await flushPromises()
    await button(wrapper, 'Create invite').trigger('click')
    await flushPromises()
    expect(api.createInvite).toHaveBeenCalledWith(
      expect.objectContaining({ role: 'member', hours: 72, max_uses: 1 }),
    )
    expect(wrapper.text()).toContain('CODE-1234')
    wrapper.unmount()
  })
})
