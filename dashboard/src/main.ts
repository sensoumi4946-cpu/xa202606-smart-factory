import { createApp } from 'vue'
import App from './App.vue'
import './styles/tokens.css'

if (new URLSearchParams(location.search).get('demo') === '1') {
  console.warn('[XA-202606] demo mode is disabled; this build only renders real backend data')
}

createApp(App).mount('#app')
