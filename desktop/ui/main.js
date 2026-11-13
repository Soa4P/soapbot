/**
 * Probe the local panel and either hand over to it or explain why it is not there.
 *
 * No framework and no build step: this document is three elements and one fetch. A
 * bundler here would add a second toolchain to a shell whose whole job is "open a URL".
 *
 * The probe is deliberately short (1.5 s). A localhost connection either answers in
 * milliseconds or is not listening at all; waiting longer only delays the explanation.
 */

const DEFAULT_PANEL = 'http://127.0.0.1:6185'
const PROBE_TIMEOUT_MS = 1500

const shell = document.getElementById('shell')
const statusLine = document.getElementById('status-line')
const offline = document.getElementById('card-offline')
const online = document.getElementById('card-online')
const commandEl = document.getElementById('command')
const hintLine = document.getElementById('hint-line')

/** `window.__TAURI__` exists because `withGlobalTauri` is on in tauri.conf.json. */
const tauri = window.__TAURI__

let panel = DEFAULT_PANEL

function setState(state, message) {
  shell.dataset.state = state
  statusLine.textContent = message
  offline.hidden = state !== 'offline'
  online.hidden = state !== 'online'
}

/**
 * 后端由壳拉起后需要几秒到几十秒启动（Python 冻结体 + SQLite 迁移）。离线时
 * 自动每 2 秒重探一次、最多 90 秒并显示已等待时长——操作者不必盯着「重新检测」
 * 手动点。超时后停回手动模式，避免无限轮询掩盖「服务真的没起来」这个事实。
 */
let autoPollTimer = null
const AUTO_POLL_INTERVAL_MS = 2000
const AUTO_POLL_MAX_MS = 90_000

function startAutoPoll() {
  if (autoPollTimer !== null) return
  const startedAt = Date.now()
  autoPollTimer = setInterval(() => {
    const waited = Math.round((Date.now() - startedAt) / 1000)
    if (waited > AUTO_POLL_MAX_MS / 1000) {
      clearInterval(autoPollTimer)
      autoPollTimer = null
      setState('offline', '等待超时——请确认服务已安装，或点「重新检测」')
      return
    }
    void probe(`后端启动中…（已等待 ${waited} 秒，自动重试）`)
  }, AUTO_POLL_INTERVAL_MS)
}

function stopAutoPoll() {
  if (autoPollTimer !== null) {
    clearInterval(autoPollTimer)
    autoPollTimer = null
  }
}

async function probe(statusMessage = '正在检查本机服务…') {
  setState('probing', statusMessage)
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS)
  try {
    // `no-cors` on purpose: the panel does not send CORS headers for this origin and
    // does not need to. The probe only asks "did something answer", and an opaque
    // response answers that.
    await fetch(`${panel}/api/health`, {
      signal: controller.signal,
      mode: 'no-cors',
      cache: 'no-store',
    })
    stopAutoPoll()
    setState('online', '服务已就绪')
  } catch (error) {
    console.error('health probe failed', error)
    setState('offline', '本机服务没有响应')
    startAutoPoll()
  } finally {
    clearTimeout(timer)
  }
}

async function copyCommand() {
  const text = commandEl.textContent ?? ''
  try {
    await navigator.clipboard.writeText(text)
    hintLine.textContent = '已复制。粘贴到终端执行，然后点「重新检测」。'
  } catch (error) {
    console.error('clipboard write failed', error)
    hintLine.textContent = '复制失败，请手动选中上面的命令。'
  }
}

document.getElementById('retry').addEventListener('click', () => {
  void probe()
})

document.getElementById('open').addEventListener('click', () => {
  window.location.replace(panel)
})

document.getElementById('copy').addEventListener('click', () => {
  void copyCommand()
})

async function init() {
  if (tauri?.core?.invoke) {
    try {
      panel = await tauri.core.invoke('panel_url')
      commandEl.textContent = await tauri.core.invoke('restart_hint')
    } catch (error) {
      console.error('tauri invoke failed, using defaults', error)
    }
    // The tray's "复制重启命令" cannot reach the clipboard itself without a plugin, so it
    // asks this page to do it — the page is already allowed to.
    await tauri.event?.listen?.('soapbot://copy-restart', (event) => {
      commandEl.textContent = event.payload
      void copyCommand()
    })
  }
  document.getElementById('port').textContent = new URL(panel).port || '6185'
  void probe()
}

void init()
