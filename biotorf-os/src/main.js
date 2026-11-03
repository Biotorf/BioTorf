import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';

import './styles/main.css';
import './styles/client.css';
import './styles/ui-polish-v2.css';

createApp(App).use(createPinia()).mount('#app');