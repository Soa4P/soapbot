import { computed, ref } from 'vue'

import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

export type Locale = 'zh-CN' | 'en-US'

const STORAGE_KEY = 'soapbot.locale'

/** The locale used when nothing has been chosen yet. */
export const DEFAULT_LOCALE: Locale = 'zh-CN'

const CATALOGUES: Record<Locale, Record<string, string>> = {
  'zh-CN': zhCN,
  'en-US': enUS,
}

function isLocale(value: unknown): value is Locale {
  return value === 'zh-CN' || value === 'en-US'
}

/**
 * The chosen language, read once at module load.
 *
 * `localStorage` throws in some privacy modes rather than returning null, so the read
 * is guarded: a panel that fails to render because a storage API is unavailable is a
 * worse outcome than a panel in the default language.
 */
function readInitialLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (isLocale(stored)) return stored
  } catch {
    // fallback: storage unavailable (private mode). Falling through to the browser
    // preference below IS the recovery, so there is nothing to report.
  }
  // The browser's own preference is a better guess than always defaulting, and it
  // costs nothing: if the operator cannot read it they will change it once.
  const preferred = navigator.language || ''
  if (preferred.toLowerCase().startsWith('en')) return 'en-US'
  return DEFAULT_LOCALE
}

export const locale = ref<Locale>(readInitialLocale())

/**
 * Keys already reported, so a missing string warns once per session.
 *
 * `t()` runs inside render functions, which run on every reactive change. Warning on
 * every call would turn one missing key into hundreds of identical console lines and
 * bury the one message that matters.
 */
const reportedMissing = new Set<string>()

/**
 * Translate `key`, with optional `{placeholder}` substitution.
 *
 * Not a template plugin: the panel has a few hundred strings, and a compiler
 * integration (`vue-i18n`) would add ~20 KB plus a build step for looked-up strings
 * that already work this way.
 *
 * A missing key never renders as an empty gap. In development it warns once and returns
 * the key, so the gap is visible in a screenshot *and* traceable to a line of code. In
 * production the key is still returned — inventing friendly text would hide the fact
 * that a translation is missing, and the key is at least searchable.
 */
export function t(key: string, params?: Record<string, string | number>): string {
  const catalogue = CATALOGUES[locale.value] ?? CATALOGUES[DEFAULT_LOCALE]
  let template = catalogue[key]
  if (template === undefined) {
    // Fall back to the default catalogue before giving up: a key that exists in zh-CN
    // but not en-US should read as Chinese, not as `memory.rows` in the middle of an
    // English page.
    template = CATALOGUES[DEFAULT_LOCALE][key]
    if (template === undefined) {
      if (import.meta.env.DEV && !reportedMissing.has(key)) {
        reportedMissing.add(key)
        console.warn(`[i18n] missing key: ${key} (locale ${locale.value})`)
      }
      return key
    }
  }
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  )
}

/**
 * Reactive `t` for computed text.
 *
 * Calling `t` inside a `computed` already tracks `locale.value`, so this exists only
 * to make the intent obvious at call sites that build strings from several keys.
 */
export function useT() {
  return computed(() => t)
}

export function setLocale(next: Locale): void {
  locale.value = next
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    // fallback: the choice will not persist across reloads, but `locale.value` is
    // already set above, so the UI switches now — which is what the click promised.
  }
  // Keep the document language in sync so a screen reader switches voice, and so
  // `:lang()` CSS has something true to match.
  document.documentElement.lang = next
}

export function availableLocales(): Locale[] {
  return Object.keys(CATALOGUES) as Locale[]
}

/** Apply the persisted language to `<html lang>` at startup. */
export function applyInitialLocale(): void {
  document.documentElement.lang = locale.value
}

/** Keys present in one catalogue and missing from the other. For the test only. */
export function catalogueKeys(loc: Locale): string[] {
  return Object.keys(CATALOGUES[loc]).sort()
}
