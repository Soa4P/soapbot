<script setup lang="ts">
/**
 * The step that used to be a second piece of software.
 *
 * "Install NapCat, log your QQ in, then type its address here" is three tasks, two of which
 * happen outside this panel. Where the host has Docker the panel can do the first two
 * itself: start the official image on loopback, hand back the QR NapCat prints, and — once
 * the scan completes — the address is already known because the panel chose the port.
 *
 * Where the host has no Docker (the usual Windows install) the component stops pretending:
 * it says so, and offers what is actually possible — open the WebUI of the NapCat that is
 * already installed there, scan in that window, then use the scan button on the adapter
 * table below. Installing a QQ client silently is not a favour.
 *
 * Polling is deliberate rather than push: a cold start pulls about a gigabyte, and a
 * spinner that keeps saying "starting" for three minutes is honest about it.
 */
import qrcode from 'qrcode-generator'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api, type NapcatStatus } from '@/api/client'
import { t } from '@/i18n'
import { copyText } from '@/lib/clipboard'
import { refreshWouldDisrupt } from '@/lib/polling'

const state = ref<NapcatStatus | null>(null)
const error = ref('')
const qrSvg = ref('')
const busy = ref(false)
let timer: number | undefined

/** QR state is visible on purpose. A picture that silently goes stale while the caption
 * promises "it refreshes automatically" is exactly the failure this component had: the
 * backend was rate-limited, every refresh failed, and the operator kept scanning a dead
 * code with no way to tell. Now the age, the last error and the next attempt are shown. */
const qrFetchedAt = ref(0)
const qrError = ref('')
const qrNextAttemptAt = ref(0)
const qrAgeSeconds = ref(0)
let qrInFlight = false

/**
 * Draw the QR ourselves from the URL NapCat hands back.
 *
 * NapCat's `GetQQLoginQrcode` returns a **URL** (`https://txz.qq.com/p?k=…`), not an image —
 * its own WebUI draws that URL in the browser. Sending it to a third-party QR service would
 * leak a live login link to that service, so the drawing happens locally.
 */
function renderQr(url: string): string {
  const qr = qrcode(0, 'M')
  qr.addData(url)
  qr.make()
  // Margin: scanners need a quiet zone, and the card already provides a white background.
  return qr.createSvgTag({ cellSize: 4, margin: 2 })
}

/** NapCat's login QR is short-lived. Re-fetch before it expires, but never hammer the
 * WebUI: each QR call used to drive a fresh /api/auth/login, and NapCat rate-limits that
 * endpoint (loginRate=10). Three-second polling locked the panel out of its own WebUI. */
const QR_TTL_MS = 60_000
/** How long to wait before asking again when the code cannot change by itself.
 * NapCat stops minting new QR codes after one expires; re-asking every 3 seconds only
 * adds load without ever producing a different URL. */
const QR_STALE_RETRY_MS = 30_000
const QR_RETRY_MS = 5_000

function describeQrFailure(reason: string): string {
  if (reason.includes('webui-rate-limited')) return t('napcat.qrRateLimited')
  if (reason.includes('webui-login-failed')) return t('napcat.qrLoginFailed')
  if (reason.includes('webui-not-ready')) return t('napcat.qrNotReady')
  if (reason.includes('webui-unreachable')) return t('napcat.qrUnreachable')
  return t('napcat.qrFailed', { reason: reason.slice(0, 80) })
}

async function fetchQr(): Promise<void> {
  if (qrInFlight) return
  qrInFlight = true
  try {
    const body = await api.napcatQr()
    if (body.error === 'already-logged-in') {
      // Not a failure: the scan completed while this poll was in flight. Clear the
      // picture instead of painting an error over a success.
      qrSvg.value = ''
      qrFetchedAt.value = 0
      qrAgeSeconds.value = 0
      qrError.value = ''
      qrNextAttemptAt.value = 0
      return
    }
    if (!body.url) throw new Error(body.error ?? 'no-qrcode')
    qrSvg.value = renderQr(body.url)
    // NapCat can answer 200 with the very same URL for hours after its QR expired
    // (coreReady=false, ErrCode 10). The backend flags that; show it instead of claiming
    // a successful refresh. The picture stays because it is the only one available.
    qrFetchedAt.value = Date.now() - (body.age_seconds ?? 0) * 1000
    qrAgeSeconds.value = Math.floor(body.age_seconds ?? 0)
    qrError.value = body.stale ? t('napcat.qrStale') : ''
    // A stale code will stay stale on the next tick — NapCat is not minting new ones —
    // so back off. Resetting this to 0 made the 3s poller re-ask forever.
    qrNextAttemptAt.value = body.stale ? Date.now() + QR_STALE_RETRY_MS : 0
  } catch (err) {
    // Do NOT swallow this. The old `catch { /* keep polling */ }` left a stale picture on
    // screen with a caption claiming it would refresh, which is why nobody could log in.
    qrError.value = describeQrFailure((err as { message?: string }).message ?? '')
    qrNextAttemptAt.value = Date.now() + QR_RETRY_MS
  } finally {
    qrInFlight = false
  }
}

async function refresh(): Promise<void> {
  try {
    state.value = await api.napcatStatus()
    error.value = ''
    const loggedIn = state.value.logged_in
    // OneBot answering is the end of the QR step: NapCat only opens that port once a QQ
    // account is scanned in. Leaving the picture up after a successful scan is how the card
    // keeps saying "scan me" at someone who already did — the panel now names the account.
    if (loggedIn) {
      qrSvg.value = ''
      qrError.value = ''
      qrFetchedAt.value = 0
      return
    }
    if (qrFetchedAt.value) {
      qrAgeSeconds.value = Math.floor((Date.now() - qrFetchedAt.value) / 1000)
    }
    const waitingForScan = state.value.status === 'running' || state.value.webui_reachable
    const now = Date.now()
    const stale = qrFetchedAt.value > 0 && now - qrFetchedAt.value > QR_TTL_MS
    const needFirst = !qrSvg.value && !qrFetchedAt.value
    if (waitingForScan && (stale || needFirst) && now >= qrNextAttemptAt.value) {
      await fetchQr()
    }
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function start(): Promise<void> {
  busy.value = true
  try {
    // Returns immediately: the pull happens in the background on the server, and this
    // screen polls until the WebUI answers.
    const body = await api.napcatStart()
    if (!body.ok) error.value = t('napcat.noDocker')
    await refresh()
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    busy.value = false
  }
}

async function stop(): Promise<void> {
  busy.value = true
  try {
    await api.napcatStop()
    qrSvg.value = ''
    qrFetchedAt.value = 0
    qrError.value = ''
    await refresh()
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    busy.value = false
  }
}

async function showQr(): Promise<void> {
  busy.value = true
  error.value = ''
  qrNextAttemptAt.value = 0 // a deliberate click always gets one attempt
  await fetchQr()
  busy.value = false
}

/* ------------------------------------------------- connect (the whole point) */
const connectNote = ref('')
const needsRestart = ref(false)

async function connect(): Promise<void> {
  busy.value = true
  connectNote.value = ''
  try {
    const body = await api.napcatConnect()
    if (body.written) {
      connectNote.value = t('napcat.connected', { account: body.account || '?' })
      needsRestart.value = true
    } else {
      // Already correct: nothing to restart, nothing to explain.
      connectNote.value = t('napcat.alreadyConnected')
    }
  } catch (err) {
    // The common wall after a scan: NapCat is logged in but has no OneBot server to connect
    // to. The backend writes that config; the person needs to know a restart applies it.
    const reason = (err as { message?: string }).message ?? ''
    connectNote.value = reason.includes('onebot-server-missing')
      ? t('napcat.onebotServerMissing')
      : t('napcat.connectNotReady')
    if (reason.includes('onebot-server-missing')) {
      needsRestart.value = true
      await refresh()
    }
  } finally {
    busy.value = false
  }
}

async function restart(): Promise<void> {
  busy.value = true
  connectNote.value = t('napcat.restarting')
  try {
    await api.napcatRestart()
  } catch {
    // 409: nothing supervises this process, so say what to type instead of pretending.
    connectNote.value = t('napcat.restartManual')
    needsRestart.value = true
  } finally {
    busy.value = false
  }
}

/** Open NapCat's WebUI *with its token*: without it the page is a login form asking for a
 * secret that lives in a log the operator has never read. */
const tokenCopied = ref(false)
const tokenCopyFailed = ref('')

async function copyToken(): Promise<void> {
  const token = state.value?.webui_token ?? ''
  if (!token) return
  tokenCopyFailed.value = ''
  if (await copyText(token)) {
    tokenCopied.value = true
    window.setTimeout(() => {
      tokenCopied.value = false
    }, 2000)
    return
  }
  tokenCopyFailed.value = t('napcat.tokenCopyFailed', { token })
}

function openWebui(): void {
  const current = state.value
  if (!current) return
  const url = current.webui_token
    ? `${current.webui_url}/webui?token=${encodeURIComponent(current.webui_token)}`
    : current.webui_url
  window.open(url, '_blank', 'noopener')
}

const canManage = computed(() => state.value?.docker === true)
/** A NapCat that is already running (installed by hand, no Docker anywhere) is the common
 * case on Windows — the card must not talk about Docker when the protocol end is right
 * there waiting for a scan. */
const foundLocally = computed(() => state.value?.webui_reachable === true)

const statusText = computed(() => {
  const current = state.value
  if (!current) return ''
  if (current.logged_in) return t('napcat.loggedIn', { account: current.account || '?' })
  if (foundLocally.value) return t('napcat.foundLocal')
  if (!current.docker) return t('napcat.noDocker')
  if (current.starting || current.status === 'created') return t('napcat.starting')
  if (current.status === 'running') return t('napcat.running')
  return t('napcat.absent')
})

onMounted(async () => {
  await refresh()
  // One second would hammer docker on a laptop; three keeps the QR step responsive.
  // The QR step is exactly where someone is typing a token into another window, so the
  // shared "would this be disruptive" rule applies here too — a refresh mid-typing used
  // to repaint the card and drop the caret.
  timer = window.setInterval(() => {
    if (refreshWouldDisrupt()) return
    void refresh()
  }, 3000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <section class="panel">
    <h2>{{ t('napcat.title') }}</h2>
    <p class="muted">{{ foundLocally ? t('napcat.hintLocal') : t('napcat.hint') }}</p>

    <p class="napcat__state">
      <span class="tag" :class="state?.logged_in ? 'ok' : canManage ? 'warn' : 'idle'">
        {{ statusText }}
      </span>
      <code v-if="state?.ws_url" class="napcat__url">{{ state.ws_url }}</code>
    </p>

    <div class="row">
      <button
        v-if="canManage && state?.status !== 'running'"
        class="btn lamp"
        type="button"
        :disabled="busy || state?.starting"
        @click="start"
      >
        {{ state?.starting ? t('napcat.starting') : t('napcat.start') }}
      </button>
      <button v-if="canManage || foundLocally" class="btn" type="button" @click="showQr">
        {{ t('napcat.showQr') }}
      </button>
      <button v-if="canManage && state?.status === 'running'" class="btn ghost" type="button" @click="stop">
        {{ t('napcat.stop') }}
      </button>
      <button
        v-if="state?.logged_in"
        class="btn lamp"
        type="button"
        :disabled="busy"
        @click="connect"
      >
        {{ t('napcat.connect') }}
      </button>
      <button v-if="needsRestart" class="btn ghost" type="button" :disabled="busy" @click="restart">
        {{ t('napcat.restart') }}
      </button>
      <button class="btn ghost" type="button" @click="openWebui">
        {{ t('napcat.openWebui') }}
      </button>
    </div>

    <!-- `v-html` is safe here by construction: the string is produced by
         qrcode-generator's `createSvgTag` from a URL we fetched ourselves, never from
         user input or a server response body. Drawing it locally is also the point —
         sending the login URL to an image service would leak a live credential. -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-if="qrSvg" class="napcat__qr" v-html="qrSvg" />
    <p v-if="qrSvg" class="muted">{{ t('napcat.qrHint') }}</p>

    <!-- The age is shown so "auto refresh" is verifiable rather than a promise. When a
         refresh fails the old picture stays (it may still be scannable) but is explicitly
         marked as possibly stale, with the reason and a manual retry. -->
    <p v-if="qrSvg && qrFetchedAt" class="muted napcat__qr-age">
      {{ t('napcat.qrAge', { seconds: qrAgeSeconds, ttl: QR_TTL_MS / 1000 }) }}
      <button class="btn ghost" type="button" :disabled="busy" @click="showQr">
        {{ t('napcat.qrRefreshNow') }}
      </button>
    </p>
    <p v-if="qrError" class="warn-banner" role="status">
      {{ qrError }}
      <button class="btn ghost" type="button" :disabled="busy" @click="showQr">
        {{ t('napcat.qrRefreshNow') }}
      </button>
    </p>

    <!-- NapCat's WebUI wants a token on first open; making the operator read a startup log
         for it is exactly the "go read the docs" move this card exists to prevent. -->
    <div v-if="foundLocally && state?.webui_token" class="napcat__token">
      <span class="hint">{{ t('napcat.tokenLabel') }}</span>
      <code class="napcat__url">{{ state.webui_token }}</code>
      <button class="btn ghost" type="button" @click="copyToken">
        {{ tokenCopied ? t('napcat.tokenCopied') : t('napcat.tokenCopy') }}
      </button>
    </div>
    <p v-if="tokenCopyFailed" class="warn-banner" role="alert">{{ tokenCopyFailed }}</p>
    <p v-if="connectNote" class="muted">{{ connectNote }}</p>
    <p v-if="error" class="muted">{{ error }}</p>
  </section>
</template>

<style scoped>
.napcat__state {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 0 0 10px;
}
.napcat__url {
  font-family: var(--mono);
}
/* Fixed size so the card does not jump when the image arrives, and a white background
   because a QR on a dark panel scans badly. */
.napcat__qr {
  display: block;
  width: 220px;
  margin: 10px 0 6px;
  background: #fff;
  padding: 8px;
  border-radius: 6px;
}
/* The generated SVG carries a white background and a quiet zone; scale it to the card. */
.napcat__qr :deep(svg) {
  display: block;
  width: 100%;
  height: auto;
}
</style>
