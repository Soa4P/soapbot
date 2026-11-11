/**
 * ChatView behaviours added with the conversation feature and history paging.
 *
 * The component is mounted against a mocked `chatApi` and a stubbed EventSource:
 * the point is the wiring decisions, not the transport — first screen = newest page,
 * "load earlier" prepends, talk mode posts instead of noting, the session list
 * refreshes on a timer without dropping the selection.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const replace = vi.fn()

// `vi.hoisted`: the factory below runs before any top-level const, so the mock table
// must be born hoisted too or the component import reads undefined.
const chatApi = vi.hoisted(() => ({
  surfaces: vi.fn(async () => ({ web: true, app: false, desktop: false, talk: true })),
  me: vi.fn(async () => ({ id: 3, username: 'bob', role: 'member', sessions: [] })),
  sessions: vi.fn(async () => ({
    sessions: [
      { session_key: 'web:private:account-3', message_count: 2, last_at: 0 },
      { session_key: 'qq:group:1', message_count: 5, last_at: 0 },
    ],
    scope: 'member',
  })),
  messages: vi.fn(async (_key: string, opts: { beforeId?: number } = {}) => ({
    session_key: _key,
    messages: opts.beforeId
      ? [{ id: opts.beforeId - 1, session_key: _key, role: 'user', content: 'earlier', created_at: 0 }]
      : [{ id: 10, session_key: _key, role: 'user', content: 'newest', created_at: 0 }],
    has_older: Boolean(opts.beforeId),
  })),
  talk: vi.fn(async () => ({ session_key: 'web:private:account-3', reply: 'pong', trace_id: 't' })),
  note: vi.fn(),
  streamUrl: vi.fn(() => '/api/chat/stream'),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}))

vi.mock('@/api/client', () => ({
  ApiError: class ApiError extends Error {
    constructor(public status: number) {
      super('api')
    }
  },
  chatApi,
}))

import ChatView from './ChatView.vue'

class FakeEventSource {
  static last: FakeEventSource | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  constructor() {
    FakeEventSource.last = this
  }
  close(): void {}
}

const mk = (id: number, content: string, role = 'user') => ({
  id,
  session_key: 'web:private:account-3',
  role,
  content,
  created_at: 0,
})

describe('ChatView paging and talk', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', FakeEventSource)
    window.matchMedia = window.matchMedia || (() => ({ matches: false }) as MediaQueryList)
    Element.prototype.scrollTo = Element.prototype.scrollTo || (() => {})
    chatApi.me.mockClear()
    chatApi.sessions.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  async function mountView() {
    const wrapper = mount(ChatView, { attachTo: document.body })
    await flushPromises()
    // bootstrap auto-opens the first session; the list is ordered talk-first.
    return wrapper
  }

  it('opens the newest page and hides the load-earlier button when history ends', async () => {
    chatApi.messages.mockResolvedValueOnce({
      session_key: 'web:private:account-3',
      messages: [mk(9, 'a'), mk(10, 'b')],
      has_older: false,
    })
    const wrapper = await mountView()
    expect(chatApi.messages).toHaveBeenCalledWith('web:private:account-3', {
      latest: true,
      limit: 100,
    })
    expect(wrapper.find('.chat__earlier').exists()).toBe(false)
    wrapper.unmount()
  })

  it('prepends the previous page and removes the button once history ends', async () => {
    chatApi.messages.mockResolvedValueOnce({
      session_key: 'web:private:account-3',
      messages: [mk(9, 'a'), mk(10, 'b')],
      has_older: true,
    })
    const wrapper = await mountView()
    expect(wrapper.find('.chat__earlier').exists()).toBe(true)

    chatApi.messages.mockResolvedValueOnce({
      session_key: 'web:private:account-3',
      messages: [mk(8, 'older')],
      has_older: false,
    })
    await wrapper.find('.chat__earlier').trigger('click')
    await flushPromises()
    const contents = wrapper.findAll('.bubble__body').map((n) => n.text())
    expect(contents).toEqual(['older', 'a', 'b'])
    expect(wrapper.find('.chat__earlier').exists()).toBe(false)
    wrapper.unmount()
  })

  it('sends a talk message through POST /api/chat/messages and syncs the tail', async () => {
    chatApi.messages.mockResolvedValueOnce({
      session_key: 'web:private:account-3',
      messages: [mk(10, 'hi from user')],
      has_older: false,
    })
    const wrapper = await mountView()
    // The talk session is this account's own: composer shows the talk placeholder.
    const textarea = wrapper.find('textarea')
    expect((textarea.element as HTMLTextAreaElement).placeholder).toContain('bot a message')

    await textarea.setValue('ping')
    // The tail page sendTalk syncs after the POST; queue it before submitting.
    chatApi.messages.mockResolvedValueOnce({
      session_key: 'web:private:account-3',
      messages: [mk(11, 'ping'), mk(12, 'pong', 'assistant')],
      has_older: false,
    })
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(chatApi.talk).toHaveBeenCalledWith('ping')

    const contents = wrapper.findAll('.bubble__body').map((n) => n.text())
    expect(contents).toContain('ping')
    expect(contents).toContain('pong')
    wrapper.unmount()
  })

  it('keeps the note composer for sessions that are not the talk session', async () => {
    chatApi.sessions.mockResolvedValueOnce({
      sessions: [{ session_key: 'qq:group:1', message_count: 5, last_at: 0 }],
      scope: 'member',
    })
    chatApi.messages.mockResolvedValueOnce({
      session_key: 'qq:group:1',
      messages: [mk(1, 'hello')],
      has_older: false,
    })
    const wrapper = await mountView()
    const textarea = wrapper.find('textarea')
    expect((textarea.element as HTMLTextAreaElement).placeholder).toContain('Write a note')
    wrapper.unmount()
  })

  it('polls the session list on the 30s timer', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const wrapper = await mountView()
    expect(chatApi.sessions).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(31_000)
    await flushPromises()
    expect(chatApi.sessions.mock.calls.length).toBeGreaterThanOrEqual(2)
    wrapper.unmount()
  })
})
