<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { init } from 'echarts'
import { fetchLatest, type LatestDevice } from '../api'

const gaugeRef = ref<HTMLDivElement>()
const tempRef = ref<HTMLDivElement>()
const humRef = ref<HTMLDivElement>()
let gaugeChart: ReturnType<typeof init> | null = null
let timer: ReturnType<typeof setInterval> | undefined

function buildOptions(name: string, value: number, unit: string, max: number) {
  return {
    series: [{
      type: 'gauge',
      min: 0,
      max,
      detail: { formatter: `{value} ${unit}`, fontSize: 14, color: '#e2e8f0' },
      data: [{ value, name }],
      axisLine: { lineStyle: { width: 12, color: [[0.5, '#38bdf8'], [0.8, '#fbbf24'], [1, '#ef4444']] } },
    }],
  }
}

async function refresh() {
  try {
    const data = await fetchLatest('sensor_dht22_01')
    const dev = data.find((d: LatestDevice) => d.device_id === 'sensor_dht22_01')
    if (!dev || !gaugeChart) return
    const temp = dev.measurements.find((m) => m.type === 'temperature')
    const hum = dev.measurements.find((m) => m.type === 'humidity')
    gaugeChart.setOption(buildOptions('Temperature', temp?.value ?? 0, '°C', 60), true)
  } catch { /* ignore */ }
}

onMounted(() => {
  if (gaugeRef.value) {
    gaugeChart = init(gaugeRef.value)
    refresh()
    timer = setInterval(refresh, 2000)
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  gaugeChart?.dispose()
})
</script>

<template>
  <div class="panel">
    <h3>温湿度监测</h3>
    <div ref="gaugeRef" class="chart"></div>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
.chart { width: 100%; height: 220px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 8px; }
</style>
