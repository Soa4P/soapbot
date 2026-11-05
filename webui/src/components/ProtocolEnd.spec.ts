/**
 * The QR card is where "根本登不进去" happened, twice.
 *
 * First every poll re-logged-in until NapCat rate-limited the panel, and the failure was
 * swallowed. Then a stale code was re-fetched every 3 seconds with a caption promising it
 * would refresh. And a QR request after a successful scan came back as "QQ Is Logined",
 * which the card painted as an error at the moment everything started working.
 *
 * These tests pin the three behaviours, not the markup.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { NapcatStatus } from '@/api/client'

vi.mock('@/api/client', () => ({
  api: {
    napcatStatus: vi.fn(),
    napcatQr: vi.fn(),
    napcatStart: vi.fn(),
    napcatConnect: vi.fn(),
    napcatStop: vi.fn(),
  },
}))

import { api } from '@/api/client'
import ProtocolEnd from './ProtocolEnd.vue'

const mocked = api as unknown as {
  napcatStatus: ReturnType<typeof vi.fn>
  napcatQr: ReturnType<typeof vi.fn>
}

function status(overrides: Partial<NapcatStatus> = {}): NapcatStatus {
  return {
    docker: false,
    exists: false,
    status: 'no-docker',
    starting: false,
    image: 'img',
    ws_url: 'ws://127.0.0.1:3001',
    webui_url: 'http://127.0.0.1:6099',
    webui_token: 'tok',
    access_token: '',
    webui_reachable: true,
    logged_in: false,
    account: '',
    phase: 'waiting_qrcode',
    ...overrides,
  }
}

async function mountCard() {
  const wrapper = mount(ProtocolEnd)
  await flushPromises()
  return wrapper
}

describe('ProtocolEnd QR card', () => {
  beforeEach(() => {
    vi.useRealTimers()
    mocked.napcatStatus.mockReset()
    mocked.napcatQr.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does not ask for a QR once QQ is logged in', async () => {
    mocked.napcatStatus.mockResolvedValue(status({ logged_in: true, account: '2268360864' }))

    const wrapper = await mountCard()

    expect(mocked.napcatQr).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('2268360864')
    wrapper.unmount()
  })

  it('treats "already logged in" as success, not as a QR failure', async () => {
    // The race: the scan lands between a status poll and a QR poll, so NapCat answers
    // "QQ Is Logined". This used to render an error banner over a working login.
    mocked.napcatStatus.mockResolvedValue(status({ webui_reachable: true, phase: 'waiting_qrcode' }))
    mocked.napcatQr.mockResolvedValue({ ok: false, error: 'already-logged-in' })

    const wrapper = await mountCard()
    // Drive one explicit fetch, as the "show QR" button would.
    await wrapper.findAll('button').find((b) => b.text().length > 0)?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('already-logged-in')
    expect(wrapper.text()).not.toContain('Could not fetch')
    wrapper.unmount()
  })

  it('backs off instead of re-asking every poll while the code is stale', async () => {
    // Fake timers on purpose: the poller runs every 3s, so a real-time wait would never
    // reach a tick and the assertion below would pass no matter what the code did.
    vi.useFakeTimers()
    mocked.napcatStatus.mockResolvedValue(status({ webui_reachable: true }))
    mocked.napcatQr.mockResolvedValue({
      ok: true,
      url: 'https://txz.qq.com/p?k=DEAD',
      age_seconds: 400,
      stale: true,
    })

    const wrapper = mount(ProtocolEnd)
    // Let mount's status call resolve, then drive the poller through several ticks.
    await vi.advanceTimersByTimeAsync(50)
    const afterFirst = mocked.napcatQr.mock.calls.length
    expect(afterFirst).toBeGreaterThan(0)

    await vi.advanceTimersByTimeAsync(10_000)
    await flushPromises()

    // 10s is more than three poller ticks. Without the stale backoff this would be
    // afterFirst + 3; the retry window is 30s, so it must stay put.
    expect(mocked.napcatQr.mock.calls.length).toBe(afterFirst)
    wrapper.unmount()
    vi.useRealTimers()
  })
})
