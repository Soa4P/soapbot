import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

/**
 * The bundle is written straight into the Python package.
 *
 * Serving it from a second location would mean the wheel and the UI could be at
 * different versions — the classic "the panel shows a field the API removed" bug.
 * Emitting into `src/soapbot/webui/dist` puts both on one build artifact and one
 * version number.
 */
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: '../src/soapbot/webui/dist',
    emptyOutDir: true,
    // Sourcemaps in an admin panel hand a casual attacker a map of every endpoint and
    // comment. They cost nothing to omit on a bundle that ships to operators.
    sourcemap: false,
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
    proxy: {
      // Dev only: the FastAPI origin. Keeping the proxy means the client can use
      // relative URLs in both dev and production, so there is no environment-specific
      // base URL to get wrong at deploy time.
      '/api': {
        target: 'http://127.0.0.1:6185',
        changeOrigin: false,
      },
    },
  },
})
