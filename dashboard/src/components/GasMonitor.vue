<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { init } from 'echarts'
import { fetchHistory } from '../api'
import { deviceForSubsystem } from '../subsystemDevices'

const chartRef = ref<HTMLDivElement>()
const loading = ref(true)
const error = ref('')
let chart: ReturnType<typeof init> | null = null
let timer: ReturnType<typeof setInterval> | undefined

const SERIES = [
  { key: 'co', name: '一氧化碳', unit: 'ppm', axis: 0, color: '#e69f00', danger: 35 },
  { key: 'smoke', name: '烟雾', unit: 'ppm', axis: 1, color: '#56b4e9', danger: 8 },
  { key: 'combustible_gas', name: '可燃气体', unit: 'ppm', axis: 1, color: '#cc79a7', danger: 3 },
]

async function refresh() {
  const dev = deviceForSubsystem('gas')
  if (!dev) {
    loading.value = false
    error.value = '未发现气体子系统设备'
    return
  }
  try {
    const since = new Date(Date.now() - 600_000).toISOString()
    const until = new Date().toISOString()
    const data = await fetchHistory({
      device_id: dev.deviceId,
      since,
      until,
      limit: 60,
    })
    const items = [...data.items].reverse()
    error.value = ''
    loading.value = false
    await nextTick()
    if (!chart) return
    chart.resize()

    const times = items.map((r) =>
      new Date(r.timestamp).toLocaleTimeString('zh-CN', { hour12: false }),
    )

    chart.setOption({
      animation: false,
      textStyle: { fontFamily: 'inherit', fontSize: 11 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#1f262e',
        borderColor: '#3a434e',
        textStyle: { color: '#e8eaed', fontSize: 11 },
      },
      legend: {
        data: SERIES.map((s) => s.name),
        textStyle: { color: '#9aa3af', fontSize: 11 },
        top: 0,
        itemWidth: 14,
        itemHeight: 2,
      },
      grid: { left: 44, right: 44, top: 26, bottom: 22 },
      xAxis: {
        type: 'category',
        data: times,
        axisLine: { lineStyle: { color: '#2a313a' } },
        axisLabel: { color: '#6b7480', fontSize: 10 },
      },
      yAxis: [
        {
          type: 'value',
          name: 'CO ppm',
          nameTextStyle: { color: '#6b7480', fontSize: 10 },
          min: 0,
          splitLine: { lineStyle: { color: '#22282f' } },
          axisLabel: { color: '#6b7480', fontSize: 10 },
        },
        {
          type: 'value',
          name: '烟雾 / 可燃气 ppm',
          nameTextStyle: { color: '#6b7480', fontSize: 10 },
          min: 0,
          max: 20,
          splitLine: { show: false },
          axisLabel: { color: '#6b7480', fontSize: 10 },
        },
      ],
      series: SERIES.map((s) => ({
        name: s.name,
        type: 'line',
        yAxisIndex: s.axis,
        showSymbol: false,
        lineStyle: { width: 1.5, color: s.color },
        itemStyle: { color: s.color },
        data: items.map(
          (r) => r.measurements.find((m) => m.type === s.key)?.value ?? null,
        ),
        markLine: {
          silent: true,
          symbol: 'none',
          label: {
            formatter: `${s.name}阈值`,
            color: '#6b7480',
            fontSize: 9,
            position: 'insideEndTop',
          },
          lineStyle: { color: s.color, type: 'dashed', width: 1, opacity: 0.5 },
          data: [{ yAxis: s.danger }],
        },
      })),
    })
  } catch {
    error.value = '数据加载失败'
    loading.value = false
  }
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  if (chartRef.value) chart = init(chartRef.value)
  refresh()
  timer = setInterval(refresh, 5000)
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<template>
  <div class="gas">
    <div v-if="error" class="msg">{{ error }}</div>
    <div v-else-if="loading" class="msg">读取中…</div>
    <div ref="chartRef" class="chart"></div>
    <p class="note">
      左轴为一氧化碳，右轴为烟雾与可燃气体。三者量程相差一个数量级，共用单轴会淹没小信号。
    </p>
  </div>
</template>

<style scoped>
.gas {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.chart {
  flex: 1;
  min-height: 190px;
}
.msg {
  color: var(--text-faint);
  font-size: 12px;
  padding: 6px 0;
}
.note {
  margin: 4px 0 0;
  font-size: 10px;
  color: var(--text-faint);
  line-height: 1.5;
}
</style>
