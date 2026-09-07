<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { init } from 'echarts'
import type { ForecastHistoryItem } from '../api'

const props = withDefaults(
  defineProps<{
    label: string
    unit?: string
    points: Array<{ t: string; v: number }>
    forecasts?: ForecastHistoryItem[]
  }>(),
  {
    unit: '',
    forecasts: () => [],
  },
)

const chartRef = ref<HTMLDivElement>()
let chart: ReturnType<typeof init> | null = null

function render() {
  if (!chart) return

  const actual = props.points.map((point) => [
    new Date(point.t).getTime(),
    point.v,
  ])

  const ordered = [...props.forecasts].sort(
    (a, b) =>
      new Date(a.issued_at).getTime() - new Date(b.issued_at).getTime(),
  )

  const latestPending = [...ordered]
    .reverse()
    .find((item) => item.status === 'pending')

  const latest =
    latestPending ?? (ordered.length ? ordered[ordered.length - 1] : undefined)

  const evaluated = ordered
    .filter(
      (item) =>
        item.status === 'evaluated' &&
        item.actual_value !== null,
    )
    .slice(-6)

  const chartSeries: any[] = [
    {
      name: '实测',
      type: 'line',
      data: actual,
      smooth: !['boolean', 'count'].includes(props.unit),
      step: props.unit === 'boolean' ? 'end' : false,
      showSymbol: actual.length <= 20,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { color: '#38bdf8', width: 2 },
      itemStyle: { color: '#38bdf8' },
      areaStyle: { color: 'rgba(56, 189, 248, 0.08)' },
      markLine: latest
        ? {
            silent: true,
            symbol: 'none',
            label: {
              formatter: `阈值 ${latest.threshold}`,
              position: 'insideEndTop',
              color: '#f59e0b',
              fontSize: 9,
            },
            lineStyle: {
              color: '#f59e0b',
              type: 'dashed',
              opacity: 0.7,
            },
            data: [{ yAxis: latest.threshold }],
          }
        : undefined,
    },
  ]

  if (latest) {
    const issued = new Date(latest.issued_at).getTime()
    const target = new Date(latest.target_at).getTime()
    const intervalWidth = Math.max(
      0,
      latest.predicted_ci_high - latest.predicted_ci_low,
    )

    chartSeries.push(
      {
        name: '__confidence_lower',
        type: 'line',
        stack: 'confidence',
        silent: true,
        symbol: 'none',
        data: [
          [issued, latest.current_value],
          [target, latest.predicted_ci_low],
        ],
        lineStyle: { opacity: 0 },
        areaStyle: { opacity: 0 },
        tooltip: { show: false },
      },
      {
        name: '__confidence_band',
        type: 'line',
        stack: 'confidence',
        silent: true,
        symbol: 'none',
        data: [
          [issued, 0],
          [target, intervalWidth],
        ],
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(245, 158, 11, 0.22)' },
        tooltip: { show: false },
      },
      {
        name: '10分钟预测',
        type: 'line',
        data: [
          [issued, latest.current_value],
          [target, latest.predicted_value],
        ],
        symbol: 'diamond',
        symbolSize: 7,
        lineStyle: {
          color: '#f59e0b',
          width: 2,
          type: 'dashed',
        },
        itemStyle: { color: '#f59e0b' },
      },
    )
  }

  if (evaluated.length) {
    chartSeries.push({
      name: '已验证预测',
      type: 'scatter',
      symbol: 'diamond',
      symbolSize: 7,
      data: evaluated.map((item) => [
        new Date(item.target_at).getTime(),
        item.predicted_value,
      ]),
      itemStyle: {
        color: '#a78bfa',
        borderColor: '#ddd6fe',
        borderWidth: 1,
      },
    })
  }

  chart.setOption(
    {
      animation: false,
      grid: { left: 48, right: 18, top: 52, bottom: 28 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
      },
      title: {
        text: props.unit
          ? `${props.label} (${props.unit})`
          : props.label,
        textStyle: {
          color: '#94a3b8',
          fontSize: 11,
          fontWeight: 'normal',
        },
        left: 0,
        top: 0,
      },
      legend: {
        data: evaluated.length
          ? ['实测', '10分钟预测', '已验证预测']
          : ['实测', '10分钟预测'],
        right: 0,
        top: 18,
        itemWidth: 14,
        itemHeight: 7,
        textStyle: { color: '#94a3b8', fontSize: 9 },
      },
      xAxis: {
        type: 'time',
        axisLabel: {
          color: '#64748b',
          fontSize: 9,
          formatter: '{HH}:{mm}:{ss}',
        },
        axisLine: { lineStyle: { color: '#334155' } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: '#64748b', fontSize: 9 },
        splitLine: { lineStyle: { color: '#273244' } },
      },
      series: chartSeries,
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

watch(
  [() => props.points, () => props.forecasts],
  render,
  { deep: true },
)

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
  height: 190px;
}
</style>
