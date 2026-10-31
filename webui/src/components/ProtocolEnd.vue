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

const state = ref<NapcatStatus | null>(null)
const error = ref('')
const qrSvg = ref('')
const busy = ref(false)
let timer: number | undefined

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

/** NapCat's login QR lives for about two minutes. A picture that silently expires is how
 * "扫不上" happens — so it is re-fetched on a timer while the account is not logged in. */
const QR_TTL_MS = 60_000
let qrFetchedAt = 0

async function refresh(): Promise<void> {
  try {
    state.value = await api.napcatStatus()
    error.value = ''
    // Fetch the QR as soon as the panel can, instead of waiting to be asked: the operator
    // pressed "start" and the next thing they need is the picture. 409s are ignored — that
    // is "not booted yet", and the next poll tries again. Once shown, it is re-fetched on
    // the TTL above: a stale QR scanned with a phone fails, and that failure looks like a
    // broken bot rather than an expired picture.
    const waitingForScan =
      (state.value.status === 'running' || state.value.webui_reachable) &&
      !state.value.logged_in
    const stale = Date.now() - qrFetchedAt > QR_TTL_MS
    if (waitingForScan && (stale || !qrSvg.value)) {
      try {
        const body = await api.napcatQr()
        if (body.url) {
          qrSvg.value = renderQr(body.url)
          qrFetchedAt = Date.now()
        }
      } catch {
        /* keep polling */
      }
    }
    if (state.value.logged_in) qrSvg.value = ''
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
  try {
    const body = await api.napcatQr()
    qrSvg.value = body.url ? renderQr(body.url) : ''
    if (qrSvg.value) qrFetchedAt = Date.now()
    else error.value = t('napcat.qrNotReady')
  } catch (err) {
    // 409 carries a machine token (webui-login-failed vs webui-not-ready) in ApiError.status
    // detail — map it to a sentence the operator can act on instead of a bare "409".
    const reason = (err as { message?: string }).message ?? ''
    error.value = reason.includes('webui-login-failed')
      ? t('napcat.loginFailed')
      : t('napcat.qrNotReady')
  } finally {
    busy.value = false
  }
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

async function copyToken(): Promise<void> {
  const token = state.value?.webui_token ?? ''
  if (!token) return
  try {
    await navigator.clipboard.writeText(token)
    tokenCopied.value = true
    window.setTimeout(() => {
      tokenCopied.value = false
    }, 2000)
  } catch {
    /* clipboard needs a secure context; the token is on screen to select manually */
  }
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
  timer = window.setInterval(() => {
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

    <!-- Generated locally from NapCat's login URL, so no third party ever sees the token. -->
    <div v-if="qrSvg" class="napcat__qr" v-html="qrSvg" />
    <p v-if="qrSvg" class="muted">{{ t('napcat.qrHint') }}</p>

    <!-- NapCat's WebUI wants a token on first open; making the operator read a startup log
         for it is exactly the "go read the docs" move this card exists to prevent. -->
    <div v-if="foundLocally && state?.webui_token" class="napcat__token">
      <span class="hint">{{ t('napcat.tokenLabel') }}</span>
      <code class="napcat__url">{{ state.webui_token }}</code>
      <button class="btn ghost" type="button" @click="copyToken">
        {{ tokenCopied ? t('napcat.tokenCopied') : t('napcat.tokenCopy') }}
      </button>
    </div>
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
