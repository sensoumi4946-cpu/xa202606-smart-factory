<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { rawRequest } from '../api'

const online = ref(true)
const checked = ref(false)
const lastError = ref('')
let timer: ReturnType<typeof setInterval> | undefined

async function probe() {
  try {
    const res = await rawRequest('GET', '/health')
    online.value = res.ok
    lastError.value = res.ok ? '' : `HTTP ${res.status}`
  } catch (err) {
    online.value = false
    lastError.value = String(err).slice(0, 80)
  } finally {
    checked.value = true
  }
}

onMounted(() => {
  probe()
  timer = setInterval(probe, 5000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div v-if="checked && !online" class="banner">
    <span class="mark">●</span>
    <span class="text">后端服务未连接</span>
    <span class="detail mono">
      请确认 backend 已启动（端口 8000）{{ lastError ? ' · ' + lastError : '' }}
    </span>
    <button class="retry" @click="probe">重试</button>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 7px 16px;
  background: var(--danger-bg);
  border-bottom: 1px solid var(--danger);
  font-size: 12px;
}
.mark { color: var(--danger); font-size: 9px; }
.text { color: var(--danger); font-weight: 600; }
.detail { color: var(--text-dim); font-size: 11px; }
.retry {
  margin-left: auto;
  background: transparent;
  border: 1px solid var(--danger);
  color: var(--danger);
  font-size: 11px;
  padding: 2px 12px;
  cursor: pointer;
}
</style>
