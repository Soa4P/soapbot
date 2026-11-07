/**
 * The 401 handler used to be a loop waiting to happen.
 *
 * Its job is to call `refresh()`, and `refresh()` calls `/api/auth/status` — which
 * answers 401 when the session is genuinely gone, dispatching the same event that
 * started the handler. An expired cookie therefore turned one page load into a request
 * storm. These tests pin "one attempt, never a retry", and the role gate that decides
 * whether the authority form is editable at all.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: { ...actual.api, authStatus: vi.fn() },
  }
})

import { ApiError, api } from '@/api/client'
import type { AuthStatus } from '@/api/client'

import { useAuthStore } from './auth'

const mocked = api as unknown as { authStatus: ReturnType<typeof vi.fn> }

function status(overrides: Partial<AuthStatus> = {}): AuthStatus {
  return {
    mode: 'token',
    subject: 'admin',
    role: 'admin',
    expires_at: 0,
    loopback: false,
    login_available: true,
    init_token_generated: false,
    bootstrap_state: 'redeemed',
    bootstrap_path: '',
    ttl_seconds: 3600,
    ...overrides,
  }
}

describe('auth store 401 handling', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mocked.authStatus.mockReset()
  })

  it('refreshes once even when the refresh itself answers 401', async () => {
    const store = useAuthStore()
    mocked.authStatus.mockImplementation(async () => {
      // Exactly what the request layer does on a 401: dispatch the event, which the
      // shell turns into another handleUnauthorized() call, while this one is awaiting.
      void store.handleUnauthorized()
      throw new ApiError(401, 'unauthorized')
    })

    await store.handleUnauthorized()

    expect(mocked.authStatus).toHaveBeenCalledTimes(1)
    expect(store.dialogOpen).toBe(true)
    expect(store.authenticated).toBe(false)
  })

  it('does not open the dialog when the session survived the refresh', async () => {
    const store = useAuthStore()
    mocked.authStatus.mockResolvedValue(status())

    await store.handleUnauthorized()

    expect(store.dialogOpen).toBe(false)
    expect(store.authenticated).toBe(true)
    expect(store.error).toBe('')
  })

  it('clears the session and reports the reason when refresh fails', async () => {
    const store = useAuthStore()
    mocked.authStatus.mockRejectedValue(new ApiError(500, 'boom'))

    await store.refresh()

    expect(store.status).toBeNull()
    expect(store.error).toBe('boom')
  })

  it('opens the dialog on a failed refresh, replacing the stale error', async () => {
    const store = useAuthStore()
    mocked.authStatus.mockRejectedValue(new ApiError(500, 'boom'))

    await store.handleUnauthorized()

    // `openDialog()` clears `error` on purpose: it is the login form's error slot, and
    // a previous attempt's message must not appear above a fresh form.
    expect(store.dialogOpen).toBe(true)
    expect(store.error).toBe('')
  })

  it('allows a second attempt after the first finished', async () => {
    const store = useAuthStore()
    mocked.authStatus.mockRejectedValue(new ApiError(401, 'unauthorized'))

    await store.handleUnauthorized()
    await store.handleUnauthorized()

    // The guard is re-entrancy, not a permanent lock: a later 401 must still recover.
    expect(mocked.authStatus).toHaveBeenCalledTimes(2)
  })
})

describe('auth store role gate', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mocked.authStatus.mockReset()
  })

  it.each([
    ['owner', true],
    ['admin', true],
    ['member', false],
    ['anonymous', false],
  ])('treats %s as editable=%s', async (role, editable) => {
    const store = useAuthStore()
    mocked.authStatus.mockResolvedValue(status({ role }))

    await store.refresh()

    expect(store.canEditAuthority).toBe(editable)
    expect(store.canManageMemory).toBe(editable)
  })

  it('defaults to anonymous before the first status call', () => {
    const store = useAuthStore()

    expect(store.role).toBe('anonymous')
    expect(store.canEditAuthority).toBe(false)
  })
})
