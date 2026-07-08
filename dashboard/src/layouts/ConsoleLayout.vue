<script setup lang="ts">
// App shell: top tab bar + content slot + bottom StatusBar. The active tab
// is a two-way bound value so the parent decides which view to render in the
// default slot. A clock and manual refresh button sit on the right of the
// top bar; the refresh button bumps a key the parent can watch.
import { ref, onMounted, onUnmounted } from 'vue'
import StatusBar from '../components/StatusBar.vue'

const TABS = [
  { key: 'monitor', label: '监控' },
  { key: 'console', label: '调试' },
  { key: 'devices', label: '设备' },
  { key: 'system', label: '系统' },
]

const active = defineModel<string>('active', { default: 'monitor' })
const emit = defineEmits<{ refresh: [] }>()

const clock = ref(new Date().toLocaleTimeString())
let timer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  timer = setInterval(() => {
    clock.value = new Date().toLocaleTimeString()
  }, 1000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="console">
    <header class="top-bar">
      <span class="brand">XA-202606 Smart Factory</span>
      <nav class="tabs">
        <button
          v-for="t in TABS"
          :key="t.key"
          class="tab"
          :class="{ active: active === t.key }"
          @click="active = t.key"
        >
          {{ t.label }}
        </button>
      </nav>
      <div class="right">
        <span class="clock">{{ clock }}</span>
        <button class="refresh" @click="emit('refresh')">刷新</button>
      </div>
    </header>

    <main class="content">
      <slot />
    </main>

    <StatusBar />
  </div>
</template>

<style scoped>
.console {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
.top-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  background: #1e293b;
  border-bottom: 1px solid #334155;
  flex-wrap: wrap;
}
.brand {
  color: #38bdf8;
  font-weight: 600;
  font-size: 1rem;
}
.tabs {
  display: flex;
  gap: 4px;
  flex: 1;
}
.tab {
  background: transparent;
  color: #94a3b8;
  border: none;
  padding: 6px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
}
.tab:hover {
  color: #e2e8f0;
}
.tab.active {
  background: #0f172a;
  color: #38bdf8;
}
.right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.clock {
  color: #94a3b8;
  font-size: 0.82rem;
  font-family: monospace;
}
.refresh {
  background: #334155;
  color: #e2e8f0;
  border: none;
  padding: 5px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.82rem;
}
.refresh:hover {
  background: #475569;
}
.content {
  flex: 1;
  padding: 16px 24px;
}
@media (max-width: 600px) {
  .content {
    padding: 12px 14px;
  }
}
</style>
