import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { applyInitialLocale } from './i18n'
import { router } from './router'
import './styles/base.css'

// Set `<html lang>` before the first paint so a screen reader does not read the first
// screen in the wrong language and so `:lang()` rules match from the start.
applyInitialLocale()

createApp(App).use(createPinia()).use(router).mount('#app')
