<script setup lang="ts">
// Mini ECharts line chart (Phase 3B) used in the device drawer to plot a
// single measurement's recent values over time. Kept intentionally small:
// no axis clutter, one smoothed area line. Re-renders when data changes and
// disposes on unmount.
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { init } from 'echarts'

const props = defineProps<{
  label: string
  unit?: string
  points: Array<{ t: string; v: number }>
}>()

const chartRef = ref<HTMLDivElement>()
let chart: ReturnType<typeof init> | null = null

function render() {
  if (!chart) return
  const times = props.points.map((p) => new Date(p.t).toLocaleTimeString())
  const values = props.points.map((p) => p.v)
  chart.setOption(
    {
      grid: { left: 44, right: 12, top: 24, bottom: 24 },
      tooltip: { trigger: 'axis' },
      title: {
        text: props.unit ? `${props.label} (${props.unit})` : props.label,
        textStyle: { color: '#94a3b8', fontSize: 11, fontWeight: 'normal' },
        left: 0,
        top: 0,
      },
      xAxis: {
        type: 'category',
        data: times,
        axisLabel: { color: '#64748b', fontSize: 9 },
        axisLine: { lineStyle: { color: '#334155' } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: '#64748b', fontSize: 9 },
        splitLine: { lineStyle: { color: '#1e293b' } },
      },
      series: [
        {
          type: 'line',
          data: values,
          smooth: true,
          symbol: 'circle',
          symbolSize: 4,
          lineStyle: { color: '#38bdf8', width: 2 },
          itemStyle: { color: '#38bdf8' },
          areaStyle: { color: 'rgba(56, 189, 248, 0.12)' },
        },
      ],
    },
    true,
  )
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  if (chartRef.value) {
    chart = init(chartRef.value)
    render()
    window.addEventListener('resize', onResize)
  }
})

watch(() => props.points, render, { deep: true })

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<template>
  <div ref="chartRef" class="mini"></div>
</template>

<style scoped>
.mini {
  width: 100%;
  height: 140px;
}
</style>
