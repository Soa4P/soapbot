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
    /* storage unavailable: fall through to the default */
  }
  // The browser's own preference is a better guess than always defaulting, and it
  // costs nothing: if the operator cannot read it they will change it once.
  const preferred = navigator.language || ''
  if (preferred.toLowerCase().startsWith('en')) return 'en-US'
  return DEFAULT_LOCALE
}

export const locale = ref<Locale>(readInitialLocale())

/**
 * Translate `key`, with optional `{placeholder}` substitution.
 *
 * Not a template plugin: the panel has a few hundred strings, and a compiler
 * integration (`vue-i18n`) would add ~20 KB plus a build step for looked-up strings
 * that already work this way. A missing key returns the key itself so a gap is
 * visible in a screenshot rather than rendering as an empty gap.
 */
export function t(key: string, params?: Record<string, string | number>): string {
  const catalogue = CATALOGUES[locale.value] ?? CATALOGUES[DEFAULT_LOCALE]
  const template = catalogue[key] ?? CATALOGUES[DEFAULT_LOCALE][key] ?? key
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
    /* the choice simply will not persist; the UI still switches now */
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
