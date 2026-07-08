<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { fetchLatest, type LatestDevice } from '../api'

const occupancy = ref<boolean | null>(null)
const lightState = ref<boolean | null>(null)
const loading = ref(true)
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined

const statusColor = computed(() => {
  if (occupancy.value) return '#34d399'
  return '#64748b'
})
const lightColor = computed(() => {
  if (lightState.value === null) return '#64748b'
  return lightState.value ? '#fbbf24' : '#64748b'
})

async function refresh() {
  try {
    const data = await fetchLatest('sensor_pir_01')
    const dev = data.find((d: LatestDevice) => d.device_id === 'sensor_pir_01')
    error.value = ''
    loading.value = false
    if (!dev) return
    const occ = dev.measurements.find((m) => m.type === 'occupancy')
    const ls = dev.measurements.find((m) => m.type === 'light_state')
    occupancy.value = occ ? occ.value > 0 : false
    lightState.value = ls ? ls.value > 0 : false
  } catch {
    error.value = '数据加载失败'
    loading.value = false
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 2000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="panel">
    <h3>照明状态</h3>
    <div v-if="loading" class="skeleton"></div>
    <div v-else-if="error" class="hint err">{{ error }}</div>
    <div v-show="!loading && !error" class="status-grid">
      <div class="status-item">
        <span class="label">Occupancy</span>
        <span class="dot" :style="{ background: statusColor }"></span>
        <span>{{ occupancy ? '有人' : '无人' }}</span>
      </div>
      <div class="status-item">
        <span class="label">Light</span>
        <span class="dot" :style="{ background: lightColor }"></span>
        <span>{{ lightState == null ? '--' : lightState ? '开' : '关' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 12px; }
.status-grid { display: flex; flex-direction: column; gap: 16px; padding: 8px 0; }
.status-item { display: flex; align-items: center; gap: 12px; color: #e2e8f0; font-size: 1rem; }
.label { width: 100px; color: #94a3b8; }
.dot { width: 14px; height: 14px; border-radius: 50%; display: inline-block; }
.skeleton { width: 100%; height: 96px; border-radius: 6px; background: #334155; animation: pulse 1.4s ease-in-out infinite; }
.hint { padding: 32px 0; text-align: center; font-size: 0.9rem; color: #64748b; }
.hint.err { color: #ef4444; }
@keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.8; } }
</style>
