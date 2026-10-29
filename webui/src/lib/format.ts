/** Small formatting helpers. Kept in one place so every panel shows a number the same way. */

import { t } from '@/i18n'

export function num(value: unknown): string {
  const n = Number(value ?? 0)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('en-US')
}

export function compact(value: unknown): string {
  const n = Number(value ?? 0)
  if (!Number.isFinite(n)) return '—'
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

/** Uptime as `3d 04:12`, the way a rack readout would show it. */
export function uptime(seconds: unknown): string {
  const total = Math.max(0, Math.floor(Number(seconds ?? 0)))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secondsPart = total % 60
  const clock = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(
    secondsPart,
  ).padStart(2, '0')}`
  return days ? `${days}d ${clock}` : clock
}

export function datetime(epochSeconds: unknown): string {
  const value = Number(epochSeconds ?? 0)
  if (!value) return '—'
  const date = new Date(value * 1000)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

/**
 * Time of day only (`14:07:32`), for rows that are all from the last few minutes.
 *
 * The log table needs the seconds and does not need the date on every line; using
 * `datetime` there spent a third of each row repeating the day.
 */
export function clock(epochSeconds: unknown): string {
  const value = Number(epochSeconds ?? 0)
  if (!value) return '—'
  const date = new Date(value * 1000)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

/**
 * Relative timestamps are sentences, not numbers, so they follow the language.
 *
 * `t()` reads the reactive `locale`, and these run inside render or `computed`, so the
 * whole page re-renders on a switch without a refresh. Absolute timestamps
 * (`datetime`) stay in a fixed `YYYY-MM-DD HH:MM` form on purpose: an operator
 * comparing a log line against a server clock needs one unambiguous format.
 */
export function fromNow(epochSeconds: unknown): string {
  const value = Number(epochSeconds ?? 0)
  if (!value) return '—'
  const delta = Math.floor(Date.now() / 1000 - value)
  if (delta < 5) return t('time.justNow')
  if (delta < 60) return t('time.secondsAgo', { n: delta })
  if (delta < 3600) return t('time.minutesAgo', { n: Math.floor(delta / 60) })
  if (delta < 86400) return t('time.hoursAgo', { n: Math.floor(delta / 3600) })
  return t('time.daysAgo', { n: Math.floor(delta / 86400) })
}

export function untilFuture(epochSeconds: unknown): string {
  const value = Number(epochSeconds ?? 0)
  if (!value) return '—'
  const delta = Math.floor(value - Date.now() / 1000)
  if (delta <= 0) return t('time.expired')
  if (delta < 60) return t('time.secondsIn', { n: delta })
  if (delta < 3600) return t('time.minutesIn', { n: Math.floor(delta / 60) })
  if (delta < 86400) return t('time.hoursIn', { n: Math.floor(delta / 3600) })
  return t('time.daysIn', { n: Math.floor(delta / 86400) })
}

/** Ledger amounts are integer minor units; never render them as a raw float. */
export function money(minor: unknown, currency = 'CNY'): string {
  // ``undefined`` means the ledger is not configured, which is not the same as a zero
  // balance. Showing ¥0.00 there reads as "you have spent nothing", when the truth is
  // "there is no ledger".
  if (minor === null || minor === undefined || minor === '') return '—'
  const value = Number(minor)
  if (!Number.isFinite(value)) return '—'
  const symbol = currency === 'CNY' ? '¥' : ''
  return `${symbol}${(value / 100).toFixed(2)}`
}

export function truncate(text: unknown, limit = 80): string {
  const value = String(text ?? '')
  return value.length > limit ? `${value.slice(0, limit)}…` : value
}
