/**
 * The copy button is how a bootstrap token gets from the server to a browser. It looked
 * like it worked and did nothing, because `navigator.clipboard` is undefined outside a
 * secure context and every call site swallowed the failure. These tests pin the two
 * paths and, more importantly, that a real failure is reported rather than hidden.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { copyText } from './clipboard'

function setSecureContext(value: boolean): void {
  Object.defineProperty(window, 'isSecureContext', { value, configurable: true })
}

function setClipboard(impl: (() => Promise<void>) | undefined): void {
  Object.defineProperty(navigator, 'clipboard', {
    value: impl ? { writeText: vi.fn(impl) } : undefined,
    configurable: true,
  })
}

describe('copyText', () => {
  let execCommand: ReturnType<typeof vi.fn>

  beforeEach(() => {
    execCommand = vi.fn(() => true)
    document.execCommand = execCommand as unknown as typeof document.execCommand
  })

  afterEach(() => {
    vi.restoreAllMocks()
    setSecureContext(true)
  })

  it('uses the modern API when the page is a secure context', async () => {
    setSecureContext(true)
    let written = ''
    setClipboard(async () => {
      written = ''
    })
    const writeText = vi.fn(async (text: string) => {
      written = text
    })
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })

    await expect(copyText('hello')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('hello')
    expect(written).toBe('hello')
    expect(execCommand).not.toHaveBeenCalled()
  })

  it('falls back to the selection path over plain http', async () => {
    // The production case: http://<server-ip>:6185 is not a secure context, so the
    // modern object is either missing or rejects.
    setSecureContext(false)
    setClipboard(undefined)

    await expect(copyText('token-value')).resolves.toBe(true)
    expect(execCommand).toHaveBeenCalledWith('copy')
  })

  it('falls back when the modern API rejects even in a secure context', async () => {
    setSecureContext(true)
    setClipboard(async () => {
      throw new DOMException('denied', 'NotAllowedError')
    })

    await expect(copyText('token-value')).resolves.toBe(true)
    expect(execCommand).toHaveBeenCalledWith('copy')
  })

  it('reports failure instead of pretending, so callers can tell the person', async () => {
    setSecureContext(false)
    setClipboard(undefined)
    document.execCommand = vi.fn(() => false) as unknown as typeof document.execCommand

    await expect(copyText('token-value')).resolves.toBe(false)
  })

  it('does not touch the DOM for empty text', async () => {
    setSecureContext(true)
    setClipboard(undefined)

    await expect(copyText('')).resolves.toBe(false)
    expect(execCommand).not.toHaveBeenCalled()
    expect(document.querySelector('textarea')).toBeNull()
  })
})
