<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { init } from 'echarts'
import { fetchLatest, type LatestDevice } from '../api'

const chartRef = ref<HTMLDivElement>()
let chart: ReturnType<typeof init> | null = null
let timer: ReturnType<typeof setInterval> | undefined

async function refresh() {
  try {
    const data = await fetchLatest('sensor_ir_01')
    const dev = data.find((d: LatestDevice) => d.device_id === 'sensor_ir_01')
    if (!dev || !chart) return
    const cnt = dev.measurements.find((m) => m.type === 'count')
    chart.setOption({
      tooltip: {},
      grid: { left: 40, right: 16, top: 16, bottom: 24 },
      xAxis: { type: 'category', data: ['Count'] },
      yAxis: { type: 'value', name: 'items' },
      series: [{
        type: 'bar', data: [cnt?.value ?? 0],
        itemStyle: { color: '#34d399' },
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
    <h3>货物感应计数</h3>
    <div ref="chartRef" class="chart"></div>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
.chart { width: 100%; height: 220px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 8px; }
</style>
