<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { init } from 'echarts'
import { fetchHistory } from '../api'

const chartRef = ref<HTMLDivElement>()
const loading = ref(true)
const error = ref('')
let chart: ReturnType<typeof init> | null = null
let timer: ReturnType<typeof setInterval> | undefined

async function refresh() {
  try {
    const since = new Date(Date.now() - 600000).toISOString()
    const until = new Date().toISOString()
    const data = await fetchHistory({ device_id: 'sensor_mq2_01', since, until, limit: 50 })
    const items = [...data.items].reverse()
    error.value = ''
    loading.value = false
    await nextTick()
    chart?.resize()
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
  } catch {
    error.value = '数据加载失败'
    loading.value = false
  }
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  if (chartRef.value) {
    chart = init(chartRef.value)
    refresh()
    timer = setInterval(refresh, 2000)
    window.addEventListener('resize', onResize)
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<template>
  <div class="panel">
    <h3>气体浓度监测</h3>
    <div v-if="loading" class="skeleton"></div>
    <div v-else-if="error" class="hint err">{{ error }}</div>
    <div v-show="!loading && !error" ref="chartRef" class="chart"></div>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
.chart { width: 100%; height: 220px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 8px; }
.skeleton { width: 100%; height: 220px; border-radius: 6px; background: #334155; animation: pulse 1.4s ease-in-out infinite; }
.hint { padding: 90px 0; text-align: center; font-size: 0.9rem; color: #64748b; }
.hint.err { color: #ef4444; }
@keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.8; } }
@media (max-width: 600px) { .chart, .skeleton { height: 180px; } }
</style>