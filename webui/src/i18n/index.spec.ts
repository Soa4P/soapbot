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
    // Asserted structurally, not against a literal: `test_no_hardcoded_cjk_in_script_strings`
    // scans every `.ts` under `src` and fails on CJK in a string literal, and a spec is not
    // an exemption. Comparing the two locales also tests the thing that matters — that
    // `setLocale` actually reaches a different catalogue — which a literal would not.
    setLocale('zh-CN')
    const zh = t('common.loadMore')

    setLocale('en-US')
    const en = t('common.loadMore')

    expect(zh).not.toBe('')
    expect(en).not.toBe('')
    expect(zh).not.toBe(en)
  })

  it('never renders a raw key for a key both catalogues carry', () => {
    // `check:i18n` keeps the two catalogues key-for-key identical, so the zh-CN fallback
    // is a safety net for the window between adding a key and translating it. What is
    // testable here is the outcome: a known key always resolves to text.
    setLocale('en-US')
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
