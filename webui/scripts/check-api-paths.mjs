#!/usr/bin/env node
/**
 * Fail the build when the panel calls a route the backend does not serve.
 *
 * Nothing currently checks this. The panel is a static bundle, so a typo in a path
 * type-checks fine, builds fine, and shows up as a 404 to the person clicking the
 * button — which is exactly how a "Save permissions" button once looked broken while
 * the endpoint was really just spelled differently.
 *
 * Both sides are read statically so the check runs in the frontend CI job, which has no
 * Python:
 *   - backend: `APIRouter(prefix="/api/x")` plus `@router.get("/y")` in src/soapbot/api
 *   - frontend: every '/api/...' string in webui/src
 *
 * Parameter names differ between the two (`{doc_id}` vs `${id}`), so the comparison is
 * shape-based: path segments that look like parameters collapse to `:p`.
 *
 * Usage: node scripts/check-api-paths.mjs
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const webuiRoot = fileURLToPath(new URL('..', import.meta.url))
const repoRoot = join(webuiRoot, '..')
const apiDir = join(repoRoot, 'src', 'soapbot', 'api')

/** `{id}` / `${id}` / `:id` all become `:p` so the two sides can be compared. */
function normalise(path) {
  return path
    .replace(/\$\{[^}]*\}/g, ':p')
    .replace(/\{[^}]*\}/g, ':p')
    .replace(/:[A-Za-z_][A-Za-z0-9_]*/g, ':p')
    .replace(/\/+$/, '')
}

function backendRoutes() {
  const routes = new Set()
  for (const name of readdirSync(apiDir)) {
    if (!name.endsWith('.py')) continue
    const text = readFileSync(join(apiDir, name), 'utf8')
    const prefixMatch = text.match(/APIRouter\([^)]*prefix="([^"]*)"/)
    const prefix = prefixMatch ? prefixMatch[1] : ''
    for (const match of text.matchAll(/@router\.(?:get|post|put|patch|delete)\(\s*"([^"]*)"/g)) {
      routes.add(normalise(`${prefix}${match[1]}`))
    }
  }
  // A handful of routes live on the app itself (/api/health, /api/metrics) rather than
  // in a router, because they must answer before the runtime exists.
  const appText = readFileSync(join(repoRoot, 'src', 'soapbot', 'app.py'), 'utf8')
  for (const match of appText.matchAll(/@app\.(?:get|post|put|patch|delete)\(\s*"([^"]*)"/g)) {
    if (match[1].startsWith('/api/')) routes.add(normalise(match[1]))
  }
  return routes
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      if (entry === 'node_modules' || entry === 'dist') continue
      walk(full, out)
    } else if (/\.(ts|vue)$/.test(entry)) {
      out.push(full)
    }
  }
  return out
}

function frontendPaths() {
  // file -> Set of normalised paths
  const found = new Map()
  for (const file of walk(join(webuiRoot, 'src'))) {
    const text = readFileSync(file, 'utf8')
    // Backtick templates and plain strings. Stop at a quote, a space or a `?`.
    for (const match of text.matchAll(/['"`](\/api\/[^'"`\s?]*)['"`]/g)) {
      const raw = match[1]
      if (!raw.startsWith('/api/')) continue
      const key = normalise(raw)
      if (!found.has(key)) found.set(key, new Set())
      found.get(key).add(file.replace(`${webuiRoot}/`, ''))
    }
  }
  return found
}

const routes = backendRoutes()
const calls = frontendPaths()

if (routes.size === 0) {
  console.error('could not read any backend routes — did src/soapbot/api move?')
  process.exit(1)
}

const missing = []
for (const [path, files] of calls) {
  // A prefix match is allowed only when it ends at a path boundary: the panel builds
  // some URLs by appending a value, and those already normalise to `:p`.
  if (routes.has(path)) continue
  const looksDynamic = [...routes].some((route) => route.startsWith(`${path}:p`))
  if (looksDynamic) continue
  missing.push(`${path}  (in ${[...files].slice(0, 2).join(', ')})`)
}

if (missing.length) {
  console.error(`the panel calls ${missing.length} route(s) the API does not serve:`)
  for (const item of missing) console.error(`  - ${item}`)
  process.exit(1)
}

console.log(`api paths ok: ${calls.size} called, ${routes.size} served`)
