import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// Целевой адрес бэкенда для dev-прокси (backend docker compose: порт 8787).
const BACKEND = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8787';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // В dev-режиме проксируем все серверные маршруты на бэкенд — так же,
    // как это делает nginx в docker-стеке (см. nginx.conf). Это убирает
    // рассинхрон портов (502/ECONNREFUSED) при npm run dev без VITE_COMMS_API.
    proxy: {
      '/api':       { target: BACKEND, changeOrigin: true },
      '/webhooks':  { target: BACKEND, changeOrigin: true },
      '/auth':      { target: BACKEND, changeOrigin: true },
      '/health':    { target: BACKEND, changeOrigin: true },
      '/docs':      { target: BACKEND, changeOrigin: true },
      '/openapi.json': { target: BACKEND, changeOrigin: true },
    },
  },
});