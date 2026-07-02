<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { fetchLatest, type LatestDevice } from '../api'

const occupancy = ref<boolean | null>(null)
const lightState = ref<boolean | null>(null)
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
    if (!dev) return
    const occ = dev.measurements.find((m) => m.type === 'occupancy')
    const ls = dev.measurements.find((m) => m.type === 'light_state')
    occupancy.value = occ ? occ.value > 0 : false
    lightState.value = ls ? ls.value > 0 : false
  } catch {
    error.value = 'Fetch failed'
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
    <div class="status-grid">
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
    <div v-if="error" class="err">{{ error }}</div>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 12px; }
.status-grid { display: flex; flex-direction: column; gap: 16px; padding: 8px 0; }
.status-item { display: flex; align-items: center; gap: 12px; color: #e2e8f0; font-size: 1rem; }
.label { width: 100px; color: #94a3b8; }
.dot { width: 14px; height: 14px; border-radius: 50%; display: inline-block; }
.err { color: #ef4444; font-size: 0.8rem; }
</style>
