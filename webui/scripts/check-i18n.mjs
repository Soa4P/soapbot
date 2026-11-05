#!/usr/bin/env node
/**
 * Fail the build when a translation key cannot resolve.
 *
 * `t('napcat.qrStale')` with no matching entry renders the key itself — the panel shows
 * `napcat.qrStale` to a person who cannot act on it. TypeScript cannot catch this: the
 * lookup is a runtime string. The same gap let two duplicate keys ship (an object
 * literal with the same name silently keeps the last one), which only vue-tsc happened
 * to flag.
 *
 * Checks, in the order the failures actually happen:
 *   1. a key used in code is missing from zh-CN (and separately from en-US);
 *   2. the two catalogues disagree on their key sets;
 *   3. a key is defined twice in the same file (the silent-override case);
 *   4. a key is defined but never used — dead weight that hides #1.
 *
 * Usage: node scripts/check-i18n.mjs [--quiet]
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const root = new URL('../src', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const localeDir = join(root, 'i18n', 'locales')
const LOCALES = { 'zh-CN': join(localeDir, 'zh-CN.ts'), 'en-US': join(localeDir, 'en-US.ts') }

/** Keys are written as `'foo.bar': '…'` at the start of a line. */
function readKeys(path) {
  const text = readFileSync(path, 'utf8')
  const keys = []
  for (const match of text.matchAll(/^\s*'([^']+)':/gm)) keys.push(match[1])
  return keys
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      if (entry === 'node_modules' || entry === 'dist') continue
      walk(full, out)
    } else if (/\.(ts|vue)$/.test(entry) && !full.includes(`${'locales'}`)) {
      out.push(full)
    }
  }
  return out
}

/** Strip comments so an example like `t('...')` inside a doc block is not read as code. */
function stripComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/<!--[\s\S]*?-->/g, '')
}

const used = new Map()
const literals = new Set()
const prefixes = new Set()
for (const file of walk(root)) {
  const text = stripComments(readFileSync(file, 'utf8'))
  // `t('key')` — a direct lookup, so the key must exist.
  for (const match of text.matchAll(/\bt\(\s*'([^']+)'/g)) {
    if (!used.has(match[1])) used.set(match[1], [])
    used.get(match[1]).push(relative(root, file))
  }
  // Any string literal equal to a defined key also counts: `nav.01` lives in a data
  // array and reaches `t()` as a variable, which no static lookup can follow.
  for (const match of text.matchAll(/'([a-zA-Z][\w.-]*)'/g)) literals.add(match[1])
  // Template lookup: t(`scan.kind.${entry.kind}`) — every key under that prefix is
  // potentially reachable, so the prefix is what counts, not a single key.
  for (const match of text.matchAll(/`([a-zA-Z][\w.-]*\.)\$\{/g)) prefixes.add(match[1])
}

const problems = []
const catalogues = {}

for (const [name, path] of Object.entries(LOCALES)) {
  const keys = readKeys(path)
  const counts = new Map()
  for (const key of keys) counts.set(key, (counts.get(key) ?? 0) + 1)
  const duplicates = [...counts].filter(([, n]) => n > 1).map(([k]) => k)
  if (duplicates.length) {
    problems.push(`${name}: duplicate key(s) — the last one silently wins: ${duplicates.join(', ')}`)
  }
  catalogues[name] = new Set(keys)
}

for (const [key, files] of used) {
  for (const [name, keys] of Object.entries(catalogues)) {
    if (!keys.has(key)) {
      const where = [...new Set(files)].slice(0, 3).join(', ')
      problems.push(`${name}: missing '${key}' (used in ${where})`)
    }
  }
}

const zh = catalogues['zh-CN']
const en = catalogues['en-US']
if (zh && en) {
  for (const key of [...zh].filter((k) => !en.has(k))) {
    problems.push(`en-US: defined in zh-CN but not here: '${key}'`)
  }
  for (const key of [...en].filter((k) => !zh.has(k))) {
    problems.push(`zh-CN: defined in en-US but not here: '${key}'`)
  }
}

const unused = [...(zh ?? [])].filter(
  (key) =>
    !used.has(key) &&
    !literals.has(key) &&
    ![...prefixes].some((prefix) => key.startsWith(prefix)),
)
if (unused.length) {
  problems.push(
    `unused key(s) in zh-CN (${unused.length}) — delete or wire them up: ${unused.slice(0, 12).join(', ')}${
      unused.length > 12 ? ', …' : ''
    }`,
  )
}

if (problems.length) {
  console.error(`i18n check failed (${problems.length}):`)
  for (const problem of problems) console.error(`  - ${problem}`)
  process.exit(1)
}

console.log(`i18n ok: ${used.size} keys used, ${zh.size} defined per locale`)
