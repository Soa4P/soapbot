/**
 * Page 11 (community catalogue) — the signature half of the trust chain.
 *
 * The server refuses one-click install from an unsigned index with a 409. Before this,
 * the page rendered the cards and enabled the buttons anyway, so an operator learned
 * about the refusal only by clicking. What is pinned here:
 *
 *  - unsigned catalogue → the reason is shown once, and every install button is disabled;
 *  - signed catalogue → the key is shown and the buttons work;
 *  - discovery is *not* blocked by a missing signature (cards still render), which is
 *    the whole point of keeping "discover" and "install" separate.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const catalogue = vi.hoisted(() => ({
  available: true,
  signed: true,
  signature_error: '',
  signature_key_id: 'c74ba4090e4ea9ca',
  entries: [
    { name: 'mood-diary', versions: ['0.1.0'], summary: 's', author: 'a', homepage: '', repository: '', latest: '0.1.0' },
  ],
  blocked: {},
  source: 'https://example.invalid/plugins.json',
  fetched_at: 0,
  error: '',
  warnings: [],
}))

const api = vi.hoisted(() => ({
  discoverPlugins: vi.fn(async () => catalogue),
  installFromIndex: vi.fn(async () => ({ name: 'mood-diary', version: '0.1.0', approved: false })),
}))

vi.mock('@/api/client', () => ({ api }))

import CommunityPlugins from './CommunityPlugins.vue'

function mountView() {
  return mount(CommunityPlugins, { attachTo: document.body })
}

function installButtons(wrapper: ReturnType<typeof mountView>) {
  return wrapper.findAll('button').filter((b) => /0\.1\.0/.test(b.text()))
}

describe('CommunityPlugins signature state', () => {
  beforeEach(() => {
    Object.assign(catalogue, { signed: true, signature_error: '', signature_key_id: 'c74ba4090e4ea9ca' })
    api.discoverPlugins.mockClear()
    api.installFromIndex.mockClear()
  })

  it('shows the key and keeps install enabled when the index is signed', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('c74ba4090e4ea9ca')
    const buttons = installButtons(wrapper)
    expect(buttons).toHaveLength(1)
    expect(buttons[0]!.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('disables install and states the reason when the index is unsigned', async () => {
    Object.assign(catalogue, { signed: false, signature_error: '索引没有签名文件' })
    const wrapper = mountView()
    await flushPromises()
    // Discovery still works: the card is there.
    expect(wrapper.text()).toContain('mood-diary')
    expect(wrapper.text()).toContain('索引没有签名文件')
    const buttons = installButtons(wrapper)
    expect(buttons).toHaveLength(1)
    expect(buttons[0]!.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('still lists cards when the index is unsigned (discover ≠ install)', async () => {
    Object.assign(catalogue, { signed: false, signature_error: '签名校验失败' })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.findAll('article')).toHaveLength(1)
    wrapper.unmount()
  })
})
