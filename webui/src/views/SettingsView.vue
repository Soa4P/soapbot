<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ApiError, api } from '@/api/client'
import { t, locale, setLocale, availableLocales, type Locale } from '@/i18n'
import { useAsync } from '@/lib/useAsync'

/**
 * 12 · System settings.
 *
 * Four independent cards, each saving on its own — there is deliberately no page-level
 * "save everything" button. The settings are unrelated (language, voice, MCP,
 * runtime), and one button would imply a transaction that does not exist: a failed
 * voice write would look like it also rolled back the language.
 *
 * The panel language switches immediately and is stored per browser. Everything else
 * is written to `.env` and takes effect on restart — stated plainly on the card,
 * because a saved-looking toggle that does nothing until the next boot is exactly the
 * kind of quiet lie this project keeps having to remove.
 */
const info = useAsync(() => api.settings())

const values = computed<any>(() => info.data.value?.values ?? {})
const voice = computed<any>(() => info.data.value?.voice ?? {})
const mcp = computed<any>(() => info.data.value?.mcp ?? { servers: [], tools: 0 })
const schemaVersion = computed<number | null>(() => info.data.value?.schema_version ?? null)
const expectedSchema = computed<number>(() => info.data.value?.expected_schema_version ?? 0)

const saving = ref('')
const errors = ref<Record<string, string>>({})
const saved = ref<Record<string, boolean>>({})

/** Local edits, so a change is not lost while the write is in flight. */
const draftLocale = ref<string>(values.value.default_locale ?? 'zh-CN')
const draftVoiceIn = ref<boolean>(!!values.value.voice_enabled)
const draftVoiceOut = ref<boolean>(!!values.value.voice_tts_enabled)
const draftVoiceName = ref<string>(values.value.voice_tts_voice ?? '')

/**
 * Seed the editable fields from the server once the first load lands.
 *
 * `useAsync` fires on mount, so the drafts start empty; without this the selects would
 * render with no selection and saving would overwrite a good value with a blank. Only
 * the *first* load seeds: later loads (the global refresh button) must not clobber
 * edits in progress.
 */
const seeded = ref(false)
watch(
  () => info.data.value,
  (data) => {
    if (!data || seeded.value) return
    seeded.value = true
    const v = data.values ?? {}
    draftLocale.value = v.default_locale ?? 'zh-CN'
    draftVoiceIn.value = !!v.voice_enabled
    draftVoiceOut.value = !!v.voice_tts_enabled
    draftVoiceName.value = v.voice_tts_voice ?? ''
  },
  { immediate: true },
)

/**
 * Cards whose file value differs from the value the running process is using.
 *
 * This is the visible half of "written but not live". Without it, saving a toggle
 * either makes the control snap back to the old value (looks like the save failed, and
 * the operator clicks again) or leaves the new value showing as if it were in effect
 * (a lie). Neither is acceptable, so the control keeps what the operator chose and a
 * badge says the change is waiting for a restart.
 */
const pending = ref<Record<string, boolean>>({})

async function save(card: string, changes: Record<string, unknown>): Promise<void> {
  saving.value = card
  errors.value = { ...errors.value, [card]: '' }
  saved.value = { ...saved.value, [card]: false }
  try {
    const result = await api.saveSettings(changes)
    saved.value = { ...saved.value, [card]: true }
    // Do *not* reload into the draft state here: the server reports the values the
    // running process holds, which are the pre-save ones until a restart. Reloading
    // would visually undo the operator's action.
    pending.value = { ...pending.value, [card]: !!result.restart_required }
    // Fade the acknowledgement: a permanent "已保存" stops meaning anything.
    window.setTimeout(() => (saved.value = { ...saved.value, [card]: false }), 2600)
  } catch (err) {
    errors.value = {
      ...errors.value,
      [card]: err instanceof ApiError ? err.message : String(err),
    }
  } finally {
    saving.value = ''
  }
}

function switchPanelLocale(next: Locale): void {
  // Console language is per browser and needs no server round trip, so it is applied
  // and persisted directly rather than going through the settings endpoint.
  setLocale(next)
}

const replyLocaleOptions = computed(() => availableLocales())

const schemaMismatch = computed(
  () => schemaVersion.value !== null && schemaVersion.value !== expectedSchema.value,
)
</script>

<template>
  <div v-if="info.error.value" class="error-banner">{{ info.error.value }}</div>

  <div class="grid cols-2">
    <!-- ---------------------------------------------------------------- language -->
    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('settings.language.title') }}</h2>
        <span class="strip__spacer" />
        <span v-if="saved.language" class="tag ok">{{ t('settings.saved') }}</span>
        <span v-else-if="pending.language" class="tag lamp">{{ t('settings.pendingRestart') }}</span>
      </div>
      <div class="panel__body stack">
        <div class="row" style="gap: 10px">
          <label class="hint" style="min-width: 120px">{{ t('locale.label') }}</label>
          <select
            class="field"
            style="max-width: 220px"
            :value="locale"
            @change="switchPanelLocale(($event.target as HTMLSelectElement).value as Locale)"
          >
            <option value="zh-CN">{{ t('locale.zh') }}</option>
            <option value="en-US">{{ t('locale.en') }}</option>
          </select>
        </div>
        <p class="hint">{{ t('locale.hint') }}</p>

        <hr style="border: 0; border-top: 1px solid var(--border); margin: 4px 0" />

        <div class="row" style="gap: 10px">
          <label class="hint" style="min-width: 120px">{{ t('settings.language.reply') }}</label>
          <select v-model="draftLocale" class="field" style="max-width: 220px">
            <option v-for="code in replyLocaleOptions" :key="code" :value="code">{{ code }}</option>
          </select>
          <button
            class="btn"
            :disabled="saving === 'language' || draftLocale === values.default_locale"
            @click="save('language', { default_locale: draftLocale })"
          >
            {{ saving === 'language' ? t('settings.saving') : t('settings.save') }}
          </button>
        </div>
        <p class="hint">{{ t('settings.language.replyHint') }}</p>
        <p v-if="errors.language" class="error-banner">{{ errors.language }}</p>
      </div>
    </section>

    <!-- ------------------------------------------------------------------- voice -->
    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('settings.voice.title') }}</h2>
        <span class="strip__spacer" />
        <span v-if="saved.voice" class="tag ok">{{ t('settings.saved') }}</span>
        <span v-else-if="pending.voice" class="tag lamp">{{ t('settings.pendingRestart') }}</span>
      </div>
      <div class="panel__body stack">
        <label class="row" style="gap: 8px; align-items: center">
          <input
            v-model="draftVoiceIn"
            type="checkbox"
            :disabled="saving === 'voice'"
            @change="save('voice', { voice_enabled: draftVoiceIn })"
          />
          <span>{{ t('settings.voice.inbound') }}</span>
        </label>
        <p class="hint">{{ t('settings.voice.inboundHint') }}</p>

        <label class="row" style="gap: 8px; align-items: center">
          <input
            v-model="draftVoiceOut"
            type="checkbox"
            :disabled="!voice.tts_available || saving === 'voice'"
            @change="save('voice', { voice_tts_enabled: draftVoiceOut })"
          />
          <span>{{ t('settings.voice.outbound') }}</span>
        </label>
        <!-- A disabled control must say why, or it reads as a broken page. -->
        <p v-if="!voice.tts_available" class="hint">
          {{ t('settings.voice.missingExtra') }}
          <span class="mono">{{ voice.tts_install_hint }}</span>
        </p>

        <div class="row" style="gap: 10px">
          <label class="hint" style="min-width: 120px">{{ t('settings.voice.voice') }}</label>
          <input v-model="draftVoiceName" class="field" style="max-width: 240px" />
          <button
            class="btn"
            :disabled="saving === 'voice' || !draftVoiceName || draftVoiceName === values.voice_tts_voice"
            @click="save('voice', { voice_tts_voice: draftVoiceName })"
          >
            {{ saving === 'voice' ? t('settings.saving') : t('settings.save') }}
          </button>
        </div>
        <p v-if="errors.voice" class="error-banner">{{ errors.voice }}</p>
      </div>
    </section>

    <!-- --------------------------------------------------------------------- mcp -->
    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('settings.mcp.title') }}</h2>
        <span class="tag">{{ mcp.servers?.length ?? 0 }}</span>
        <span class="strip__spacer" />
        <span class="hint">{{ t('settings.mcp.tools') }}: {{ mcp.tools ?? 0 }}</span>
      </div>
      <div class="panel__body flush">
        <table v-if="mcp.servers?.length" class="data">
          <caption class="visually-hidden">{{ t('settings.mcp.title') }}</caption>
          <thead>
            <tr>
              <th scope="col">{{ t('settings.mcp.name') }}</th>
              <th scope="col">{{ t('settings.mcp.state') }}</th>
              <th scope="col" class="num">{{ t('settings.mcp.tools') }}</th>
              <th scope="col">{{ t('settings.mcp.error') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in mcp.servers" :key="row.name">
              <td class="key">{{ row.name }}</td>
              <td>
                <span class="pill" :class="row.error ? 'bad' : 'ok'">
                  <i class="dot" />{{ row.error ? t('settings.mcp.failed') : t('settings.mcp.ok') }}
                </span>
              </td>
              <td class="num">{{ row.tools }}</td>
              <td>{{ row.error || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">{{ t('settings.mcp.empty') }}</div>
      </div>
    </section>

    <!-- ----------------------------------------------------------------- runtime -->
    <section class="panel">
      <div class="panel__head">
        <h2>{{ t('settings.runtime.title') }}</h2>
      </div>
      <div class="panel__body flush">
        <table class="data">
          <caption class="visually-hidden">{{ t('settings.runtime.title') }}</caption>
          <tbody>
            <tr>
              <td class="key">{{ t('settings.runtime.version') }}</td>
              <td class="mono">{{ info.data.value?.version || '—' }}</td>
            </tr>
            <tr>
              <td class="key">{{ t('settings.runtime.schema') }}</td>
              <td class="mono">
                <span :class="schemaMismatch ? 'pill bad' : 'pill ok'">
                  <i class="dot" />{{ schemaVersion ?? '—' }}
                </span>
                <span class="hint" style="margin-left: 8px">
                  {{ t('settings.runtime.expected') }} {{ expectedSchema }}
                </span>
              </td>
            </tr>
            <tr>
              <td class="key">{{ t('settings.runtime.dataDir') }}</td>
              <td class="mono">{{ info.data.value?.data_dir || '—' }}</td>
            </tr>
            <tr>
              <td class="key">{{ t('settings.runtime.configDir') }}</td>
              <td class="mono">
                {{ info.data.value?.config_dir || '—' }}
                <!-- These two rows answer the question the panel otherwise lies about:
                     "I saved it, why is it not in effect?" A path plus a writability
                     flag separates a read-only mount from a wrong directory. -->
                <span
                  class="pill"
                  :class="info.data.value?.config_dir_writable ? 'ok' : 'bad'"
                  style="margin-left: 8px"
                >
                  <i class="dot" />{{ info.data.value?.config_dir_writable
                    ? t('settings.runtime.configWritable')
                    : t('settings.runtime.configReadOnly') }}
                </span>
              </td>
            </tr>
            <tr>
              <td class="key">{{ t('settings.runtime.configDetail') }}</td>
              <td>
                <span class="hint">{{ info.data.value?.config_dir_detail || '—' }}</span>
                <span v-if="info.data.value?.config_dir_remediation" class="hint" style="display: block">
                  {{ info.data.value.config_dir_remediation }}
                </span>
              </td>
            </tr>
            <tr>
              <td class="key">{{ t('settings.runtime.envFile') }}</td>
              <td class="mono">{{ info.data.value?.env_file || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="hint" style="padding: 10px 14px">
        {{ t('settings.runtime.restartHint') }}
      </p>
    </section>
  </div>

  <div v-if="(info.data.value?.startup_errors ?? []).length" class="warn-banner">
    {{ t('settings.runtime.startupErrors') }}
    <ul style="margin: 6px 0 0 18px">
      <li v-for="(err, i) in info.data.value?.startup_errors" :key="i" class="mono">
        {{ err }}
      </li>
    </ul>
  </div>
</template>
