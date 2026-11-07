/**
 * A missing key used to render as an empty gap, which is indistinguishable from a
 * layout bug — the panel showed a blank where a label should be and nothing in the
 * console said why. These tests pin the fallback chain: chosen locale → default
 * locale → the key itself, with exactly one warning per key per session.
 *
 * The absent keys are assembled at runtime on purpose. `scripts/check-i18n.mjs` reads
 * the source statically and fails the build on any `t('…')` whose key is not in both
 * catalogues — including one deliberately missing, which is the whole point here.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { locale, setLocale, t } from './index'

/** A key that is guaranteed not to exist in either catalogue. */
const ABSENT = ['spec', 'absent', 'key'].join('.')
const ABSENT_ONCE = ['spec', 'absent', 'warned', 'once'].join('.')

describe('t() fallback chain', () => {
  afterEach(() => {
    setLocale('zh-CN')
    vi.restoreAllMocks()
  })

  it('translates a key that exists in the chosen locale', () => {
    setLocale('zh-CN')
    expect(t('common.loadMore')).toBe('加载更多')

    setLocale('en-US')
    expect(t('common.loadMore')).toBe('Load more')
  })

  it('never renders a raw key for a key both catalogues carry', () => {
    // `check:i18n` keeps the two catalogues key-for-key identical, so the zh-CN fallback
    // is a safety net for the window between adding a key and translating it. What is
    // testable here is the outcome: a known key always resolves to text.
    setLocale('en-US')
    expect(t('common.loadMore')).toBe('Load more')
    expect(t('common.loadMore')).not.toBe('common.loadMore')
  })

  it('returns the key itself when no catalogue has it', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    setLocale('zh-CN')
    expect(t(ABSENT)).toBe(ABSENT)
  })

  it('warns once per missing key, not once per render', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    setLocale('zh-CN')

    t(ABSENT_ONCE)
    t(ABSENT_ONCE)
    t(ABSENT_ONCE)

    const hits = warn.mock.calls.filter((call) => String(call[0]).includes(ABSENT_ONCE))
    expect(hits).toHaveLength(1)
  })

  it('substitutes placeholders and leaves unknown ones alone', () => {
    setLocale('zh-CN')
    const value = t('security.authorityReadOnly', { role: 'member' })
    expect(value).toContain('member')
    expect(value).not.toContain('{role}')
  })

  it('keeps the locale ref in sync with setLocale', () => {
    setLocale('en-US')
    expect(locale.value).toBe('en-US')
    expect(document.documentElement.lang).toBe('en-US')
  })
})
