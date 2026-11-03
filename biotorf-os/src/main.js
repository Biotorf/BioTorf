import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';

import './styles/main.css';
import './styles/client.css';
import './styles/ui-polish-v2.css';

createApp(App).use(createPinia()).mount('#app');

// PWA: регистрация service worker (только в production-сборке, не в dev)
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}