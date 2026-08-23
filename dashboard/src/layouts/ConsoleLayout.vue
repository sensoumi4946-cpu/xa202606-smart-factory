<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import StatusBar from '../components/StatusBar.vue'
import BackendBanner from '../components/BackendBanner.vue'

const TABS = [
  { key: 'monitor', label: '监控' },
  { key: 'lab', label: '验证' },
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
    <BackendBanner />
    <header class="top-bar">
      <span class="brand">
        <span class="mark" aria-hidden="true"></span>
        <span class="name mono">XA-202606</span>
        <span class="title">智慧工厂安全监控平台</span>
      </span>
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
        <span class="clock mono">{{ clock }}</span>
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
  gap: 20px;
  padding: 10px 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.mark {
  width: 14px;
  height: 22px;
  border-radius: 3px;
  background: repeating-linear-gradient(
    -45deg,
    var(--warn) 0 5px,
    var(--surface-2) 5px 10px
  );
}
.name {
  color: var(--warn);
  font-weight: 700;
  font-size: var(--fs-md);
  letter-spacing: 0.06em;
}
.title {
  color: var(--text);
  font-weight: 600;
  font-size: var(--fs-md);
}
.tabs {
  display: flex;
  gap: 2px;
  flex: 1;
}
.tab {
  background: transparent;
  color: var(--text-dim);
  border: none;
  border-bottom: 2px solid transparent;
  padding: 6px 16px;
  cursor: pointer;
  font-size: var(--fs-md);
  font-family: var(--font-ui);
}
.tab:hover {
  color: var(--text);
}
.tab:focus-visible {
  outline: 2px solid var(--warn);
  outline-offset: 2px;
  border-radius: 4px;
}
.tab.active {
  color: var(--warn);
  border-bottom-color: var(--warn);
}
.right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.clock {
  color: var(--text-dim);
  font-size: var(--fs-sm);
}
.refresh {
  background: var(--surface-2);
  color: var(--text);
  border: 1px solid var(--line-strong);
  padding: 5px 14px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--fs-sm);
  font-family: var(--font-ui);
}
.refresh:hover {
  border-color: var(--warn);
  color: var(--warn);
}
.refresh:focus-visible {
  outline: 2px solid var(--warn);
  outline-offset: 2px;
}
.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: var(--gap) 24px;
  min-height: 0;
}
@media (max-width: 700px) {
  .title {
    display: none;
  }
  .content {
    padding: 12px 14px;
  }
}
</style>