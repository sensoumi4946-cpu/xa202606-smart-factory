<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { init } from 'echarts'
import { fetchHistory } from '../api'

const chartRef = ref<HTMLDivElement>()
let chart: ReturnType<typeof init> | null = null
let timer: ReturnType<typeof setInterval> | undefined

async function refresh() {
  try {
    const since = new Date(Date.now() - 600000).toISOString()
    const until = new Date().toISOString()
    const data = await fetchHistory({ device_id: 'sensor_mq2_01', since, until, limit: 50 })
    const items = [...data.items].reverse()
    if (!chart) return
    const times = items.map((r) => new Date(r.timestamp).toLocaleTimeString())
    const smoke = items.map((r) => r.measurements.find((m) => m.type === 'smoke')?.value ?? 0)
    const co = items.map((r) => r.measurements.find((m) => m.type === 'co')?.value ?? 0)
    const cg = items.map((r) => r.measurements.find((m) => m.type === 'combustible_gas')?.value ?? 0)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['Smoke', 'CO', 'Gas'], textStyle: { color: '#e2e8f0' }, top: 0 },
      grid: { left: 40, right: 16, top: 36, bottom: 24 },
      xAxis: { type: 'category', data: times },
      yAxis: { type: 'value', name: 'ppm', nameTextStyle: { color: '#94a3b8' } },
      series: [
        { name: 'Smoke', type: 'line', data: smoke, smooth: true },
        { name: 'CO', type: 'line', data: co, smooth: true },
        { name: 'Gas', type: 'line', data: cg, smooth: true },
      ],
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
    <h3>气体浓度监测</h3>
    <div ref="chartRef" class="chart"></div>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
.chart { width: 100%; height: 220px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 8px; }
</style>
