import { createApp } from 'vue'
import App from './App.vue'
import './styles/tokens.css'
import { ensureDeviceMetaLoaded } from './deviceMeta'

if (new URLSearchParams(location.search).get('demo') === '1') {
  console.warn('[XA-202606] demo mode is disabled; this build only renders real backend data')
}

ensureDeviceMetaLoaded()
createApp(App).mount('#app')