/**
 * Page 07 — provider health reaching the page that can act on it.
 *
 * The router has always counted failures, cooldowns and breaker state, and `/api/providers`
 * has always returned them; this page rendered `enabled` and a failure count and nothing
 * else. So a provider the router was *skipping* (three consecutive failures → 30 s
 * cooldown) still looked like an enabled green row, and the only state that explains "every
 * row is fine and the bot is silent" — an open breaker — was visible only on page 02.
 *
 * What is pinned here:
 *  - a cooling provider carries its remaining seconds, not just a boolean;
 *  - the last error text (already redacted server-side) is shown next to the row;
 *  - an open breaker raises a banner, a closed one does not;
 *  - a provider with traffic shows p50 latency instead of "no calls yet".
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const providers = vi.hoisted(() => ({
  providers: [
    {
      id: 'deepseek',
      kind: 'openai_compat',
      model: 'deepseek-flash',
      priority: 10,
      enabled: true,
      slots: ['chat'],
    },
  ],
  stats: {
    deepseek: {
      calls: 0,
      failures: 0,
      success_rate: 0,
      last_error: '',
      last_latency_ms: 0,
      p50_latency_ms: 0,
      p95_latency_ms: 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      consecutive_failures: 0,
      cooling_down: false,
      cooldown_remaining: 0,
    },
  },
  count: 1,
  breaker: { open: false, retry_after: 0, consecutive_total_failures: 0 },
}))

const api = vi.hoisted(() => ({
  providers: vi.fn(async () => providers),
  personas: vi.fn(async () => ({ personas: [], binding: {} })),
}))

vi.mock('@/api/client', () => ({ api }))

import ConfigView from './ConfigView.vue'

/** The page's four heavy children call their own endpoints; none of them is under test. */
const stubs = {
  Adapters: true,
  ProtocolEnd: true,
  McpServers: true,
  PersonaBindingCard: true,
}

/**
 * The page teleports the persona editor into `#persona-card-slot`, which the app shell
 * renders. Without a target Vue warns and the fragment root stops being walkable, so the
 * slot is created here the way the shell would.
 */
function makeSlot(): void {
  const slot = document.createElement('div')
  slot.id = 'persona-card-slot'
  document.body.appendChild(slot)
}

function mountView() {
  return mount(ConfigView, { global: { stubs }, attachTo: document.body })
}

function reset(): void {
  providers.stats.deepseek = {
    calls: 0,
    failures: 0,
    success_rate: 0,
    last_error: '',
    last_latency_ms: 0,
    p50_latency_ms: 0,
    p95_latency_ms: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    consecutive_failures: 0,
    cooling_down: false,
    cooldown_remaining: 0,
  }
  providers.breaker = { open: false, retry_after: 0, consecutive_total_failures: 0 }
}

describe('ConfigView provider health', () => {
  beforeEach(() => {
    makeSlot()
    reset()
    api.providers.mockClear()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows the remaining cooldown seconds and the last error on the row', async () => {
    providers.stats.deepseek = {
      ...providers.stats.deepseek,
      calls: 3,
      failures: 3,
      consecutive_failures: 3,
      cooling_down: true,
      cooldown_remaining: 12.4,
      last_error: '401 Unauthorized: invalid api key',
    }
    const wrapper = mountView()
    await flushPromises()
    // Ceil, not round: 12.4s left must not render as "12" and then look stuck.
    expect(wrapper.text()).toContain('13')
    expect(wrapper.text()).toContain('401 Unauthorized: invalid api key')
    wrapper.unmount()
  })

  it('raises a banner while the breaker is open', async () => {
    providers.breaker = { open: true, retry_after: 30.0, consecutive_total_failures: 4 }
    const wrapper = mountView()
    await flushPromises()
    const banner = wrapper.find('.warn-banner')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('30')
    expect(banner.text()).toContain('4')
    wrapper.unmount()
  })

  it('does not warn when the breaker is closed', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.warn-banner').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows p50 latency once a provider has answered', async () => {
    providers.stats.deepseek = {
      ...providers.stats.deepseek,
      calls: 7,
      p50_latency_ms: 820.4,
      last_latency_ms: 830,
    }
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('p50 820 ms')
    wrapper.unmount()
  })
})
