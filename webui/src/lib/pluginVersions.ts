/**
 * The same canonical blocklist key the backend uses (`manifest.block_key`).
 *
 * Duplicating a few lines of normalisation across the wire is cheaper than the bug it
 * prevents: the installer looks up `block_key(name, version)`, so a panel that looked
 * up ```${name}@${version}``` would say "not blocked" for exactly the versions the
 * upload refuses. `1.0` and `1.0.0` are the same release, and a blocklist entry for
 * `1.0.0` must light up a card that lists `1.0`.
 *
 * Keep this in sync with `src/soapbot/plugins/manifest.py`. `pluginVersions.spec.ts`
 * pins the cases that have actually caused a mismatch.
 */
const VERSION_RE = /^\d+\.\d+(\.\d+)?([abrc][0-9]+)?$/

export function versionKey(text: string): string {
  const value = String(text).trim()
  // Malformed values come from a third-party index, not from an installed manifest.
  // Prefix them so they can never collide with a real release key, mirroring the
  // backend's conservative handling of junk from the remote blocklist.
  if (!VERSION_RE.test(value)) return `?${value}`

  const tag = /[abrc]/.exec(value)
  const cut = tag ? tag.index : value.length
  const parts = value.slice(0, cut).split('.').map(Number)
  while (parts.length < 3) parts.push(0)
  return `${parts.join('.')}${value.slice(cut)}`
}

export function blockKey(name: string, version: string): string {
  return `${String(name).trim().toLowerCase()}@${versionKey(version)}`
}
