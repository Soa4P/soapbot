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

async function refresh(): Promise<void> {
  try {
    state.value = await api.napcatStatus()
    error.value = ''
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
    if (!qrSvg.value) error.value = t('napcat.qrNotReady')
  } catch {
    // 409 is the normal "not ready yet"; saying so beats an error banner.
    error.value = t('napcat.qrNotReady')
  } finally {
    busy.value = false
  }
}

function openWebui(): void {
  const url = state.value?.webui_url
  if (url) window.open(url, '_blank', 'noopener')
}

const canManage = computed(() => state.value?.docker === true)
const statusText = computed(() => {
  const current = state.value
  if (!current) return ''
  if (!current.docker) return t('napcat.noDocker')
  if (current.starting || current.status === 'created') return t('napcat.starting')
  if (current.status === 'running') {
    return current.logged_in
      ? t('napcat.loggedIn', { account: current.account || '?' })
      : t('napcat.running')
  }
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
    <p class="muted">{{ t('napcat.hint') }}</p>

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
      <button v-if="canManage" class="btn" type="button" @click="showQr">
        {{ t('napcat.showQr') }}
      </button>
      <button v-if="canManage && state?.status === 'running'" class="btn ghost" type="button" @click="stop">
        {{ t('napcat.stop') }}
      </button>
      <button class="btn ghost" type="button" @click="openWebui">
        {{ t('napcat.openWebui') }}
      </button>
    </div>

    <!-- Generated locally from NapCat's login URL, so no third party ever sees the token. -->
    <div v-if="qrSvg" class="napcat__qr" v-html="qrSvg" />
    <p v-if="qrSvg" class="muted">{{ t('napcat.qrHint') }}</p>
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
