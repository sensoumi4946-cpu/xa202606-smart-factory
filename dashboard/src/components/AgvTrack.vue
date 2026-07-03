<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { init } from 'echarts'
import { fetchLatest, type LatestDevice } from '../api'

const chartRef = ref<HTMLDivElement>()
let chart: ReturnType<typeof init> | null = null
let timer: ReturnType<typeof setInterval> | undefined

async function refresh() {
  try {
    const data = await fetchLatest('sensor_hcsr04_01')
    const dev = data.find((d: LatestDevice) => d.device_id === 'sensor_hcsr04_01')
    if (!dev || !chart) return
    const dst = dev.measurements.find((m) => m.type === 'distance')
    const val = dst?.value ?? 0
    chart.setOption({
      tooltip: {},
      grid: { left: 40, right: 16, top: 16, bottom: 24 },
      xAxis: { type: 'category', data: ['Distance'] },
      yAxis: { type: 'value', name: 'cm', max: 200 },
      series: [{
        type: 'bar', data: [val],
        itemStyle: { color: val < 30 ? '#ef4444' : '#38bdf8' },
      }],
    }, true)
  } catch { /* ignore */ }
}

onMounted(() => {
  if (chartRef.value) {
    chart = init(chartRef.value)
    refresh()
    timer = setInterval(refresh, 2000)
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  chart?.dispose()
})
</script>

<template>
  <div class="panel">
    <h3>AGV 避障距离</h3>
    <div ref="chartRef" class="chart"></div>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
.chart { width: 100%; height: 220px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 8px; }
</style>
