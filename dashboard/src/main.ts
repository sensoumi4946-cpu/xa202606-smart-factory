import { createApp } from 'vue'
import App from './App.vue'
import './styles/tokens.css'

// Demo mode: ?demo=1 serves simulated sensor data (see src/demo.ts).
const demoReady =
  new URLSearchParams(location.search).get('demo') === '1'
    ? import('./demo').then((m) => m.installDemoMode())
    : Promise.resolve()

demoReady.then(() => {
  createApp(App).mount('#app')
})
