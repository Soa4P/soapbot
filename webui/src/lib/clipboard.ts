/**
 * Copy text, including on the deployments where the modern API does not exist.
 *
 * `navigator.clipboard` requires a secure context. Most people run this panel as
 * `http://<server-ip>:6185` — not https, not localhost — so the API is `undefined`
 * there and every "copy" button in the panel silently did nothing. That is worst
 * exactly where it hurts most: copying the bootstrap token, which is the one string
 * a new operator must transfer by hand.
 *
 * So: try the modern API when it is actually usable, otherwise fall back to the
 * selection + execCommand path, which still works on plain HTTP in current browsers.
 * The return value is honest — callers must show something when it is false instead
 * of pretending it worked.
 */
export async function copyText(text: string): Promise<boolean> {
  if (!text) return false

  // `isSecureContext` is the actual gate, not the presence of the object: some
  // browsers expose `navigator.clipboard` on http and then reject the write.
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Denied, or blocked because focus is elsewhere. The selection path below is a
      // real answer, not a consolation prize, so take it here instead of falling out.
      return legacyCopy(text)
    }
  }
  return legacyCopy(text)
}

/** The pre-2018 path. Deprecated, but it is the only one that works over plain HTTP. */
function legacyCopy(text: string): boolean {
  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    // Off-screen, not `display: none` — a hidden element cannot be selected, so the
    // copy would fail for a reason that looks unrelated to visibility.
    area.style.position = 'fixed'
    area.style.top = '-1000px'
    area.style.left = '0'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    area.setSelectionRange(0, area.value.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch {
    return false
  }
}
