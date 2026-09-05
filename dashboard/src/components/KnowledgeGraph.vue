<script setup lang="ts">

import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { init } from 'echarts'
import {
  fetchSemanticView,
  fetchAlerts,
  fetchLatestDeduped,
  type SemanticSensor,
} from '../api'
import GateBadge from './GateBadge.vue'

const el = ref<HTMLDivElement>()
const error = ref('')
const loading = ref(true)
let chart: ReturnType<typeof init> | null = null
let timer: ReturnType<typeof setInterval> | undefined
let beatTimer: ReturnType<typeof setInterval> | undefined

let sensors: SemanticSensor[] = []
let alertedDevices = new Set<string>()
let freshDevices = new Set<string>()

const css = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()

  const SUBSYSTEM_LABELS: Record<string, string> = {
  temp_humidity: '温湿度',
  counting: '货物计数',
  lighting: '照明',
  gas: '气体监测',
  agv: 'AGV避障',
}

const PROPERTY_LABELS: Record<string, string> = {
  temperature: '温度',
  humidity: '湿度',
  count: '计数',
  occupancy: '人员状态',
  light_state: '照明状态',
  distance: '距离',
  co: '一氧化碳',
  smoke: '烟雾',
  combustible_gas: '可燃气体',
}

function buildOption() {
  const C = {
    root: css('--warn'),
    subsystem: css('--semantic'),
    sensor: css('--data-1'),
    prop: css('--text-faint'),
    line: css('--line-strong'),
    danger: css('--danger'),
    text: css('--text'),
    dim: css('--text-dim'),
  }

  interface GNode {
    id: string
    name: string
    category: number
    symbolSize: number
    itemStyle?: Record<string, unknown>
    label?: Record<string, unknown>
  }
  const nodes: GNode[] = [
    {
      id: 'factory',
      name: '工厂',
      category: 0,
      symbolSize: 46,
      itemStyle: { color: C.root },
      label: { fontSize: 13, fontWeight: 700 },
    },
  ]
  const links: Array<Record<string, unknown>> = []
  const subsystems = new Set<string>()

  for (const s of sensors) {
    if (!subsystems.has(s.subsystem)) {
      subsystems.add(s.subsystem)
      nodes.push({
        id: `sub:${s.subsystem}`,
        name: SUBSYSTEM_LABELS[s.subsystem] ?? s.subsystem,
        category: 1,
        symbolSize: 30,
        itemStyle: { color: C.subsystem },
      })
      links.push({ source: 'factory', target: `sub:${s.subsystem}` })
    }
    const alerted = alertedDevices.has(s.sensor)
    const fresh = freshDevices.has(s.sensor)
    nodes.push({
      id: s.sensor,
      name: s.sensor.replace('sensor_', ''),
      category: 2,
      symbolSize: alerted ? 32 : fresh ? 26 : 22,
      itemStyle: alerted
        ? {
            color: C.danger,
            shadowColor: C.danger,
            shadowBlur: 18,
          }
        : fresh
          ? {
              color: C.sensor,
              shadowColor: C.sensor,
              shadowBlur: 14,
            }
          : { color: C.sensor },
    })
    links.push({
      source: `sub:${s.subsystem}`,
      target: s.sensor,
      lineStyle: alerted ? { color: C.danger, width: 2.4 } : {},
    })
    for (const p of s.observes) {
      const pid = `${s.sensor}:${p}`
      nodes.push({
        id: pid,
        name: PROPERTY_LABELS[p] ?? p,
        category: 3,
        symbolSize: 10,
        itemStyle: { color: C.prop },
        label: { fontSize: 10, color: C.dim },
      })
      links.push({ source: s.sensor, target: pid })
    }
  }

  return {
    tooltip: { show: true, formatter: '{b}' },
    legend: {
      bottom: 0,
      textStyle: { color: C.dim, fontSize: 10 },
      itemWidth: 10,
      itemHeight: 10,
      data: ['工厂', '子系统', '传感器', '观测属性'],
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        center: ['50%', '45%'],
        force: {
          repulsion: 320,
          edgeLength: [50, 130],
          gravity: 0.18,
          layoutAnimation: true,
        },
        draggable: true,
        categories: [
          { name: '工厂', itemStyle: { color: C.root } },
          { name: '子系统', itemStyle: { color: C.subsystem } },
          { name: '传感器', itemStyle: { color: C.sensor } },
          { name: '观测属性', itemStyle: { color: C.prop } },
],
        
        label: { show: true, color: C.text, fontSize: 11, position: 'right' },
        lineStyle: { color: C.line, width: 1.4, curveness: 0.06 },
        emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
        data: nodes,
        links,
      },
    ],
  }
}

async function loadGraph() {
  try {
    const data = await fetchSemanticView('sensor-observations')
    sensors = data.results
    error.value = ''
  } catch {
    error.value = '语义服务不可用 — 无法加载知识图谱'
  } finally {
    loading.value = false
    await nextTick()
    chart?.resize()
    if (!error.value && chart) chart.setOption(buildOption(), true)
  }
}

async function refreshHeartbeat() {
  try {
    const latest = await fetchLatestDeduped()
    const next = new Set<string>()
    for (const d of latest) {
      if (d.measurements.some((m) => Date.now() - new Date(m.timestamp).getTime() < 6000))
        next.add(d.device_id)
    }
    const changed =
      next.size !== freshDevices.size ||
      [...next].some((d) => !freshDevices.has(d))
    freshDevices = next
    if (changed && sensors.length && chart)
      chart.setOption(buildOption(), false)
  } catch {
    /* keep last */
  }
}

async function refreshAlertHighlights() {
  try {
    const data = await fetchAlerts({ limit: 20 })
    const next = new Set<string>()
    for (const a of data.items) {
      if (Date.now() - new Date(a.triggered_at).getTime() > 60_000) continue
      for (const d of a.device_id.split('+')) next.add(d)
    }
    const changed =
      next.size !== alertedDevices.size ||
      [...next].some((d) => !alertedDevices.has(d))
    alertedDevices = next
    if (changed && sensors.length && chart) chart.setOption(buildOption(), true)
  } catch {
    /* keep highlights */
  }
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  if (el.value) {
    chart = init(el.value)
    loadGraph()
    refreshAlertHighlights()
    timer = setInterval(refreshAlertHighlights, 4000)
    beatTimer = setInterval(refreshHeartbeat, 3000)
    refreshHeartbeat()
    window.addEventListener('resize', onResize)
  }
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (beatTimer) clearInterval(beatTimer)
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<template>
  <div class="kg">
    <header class="head">
      <h3>知识图谱 · 传感器网络</h3>
      <div class="meta">
        <GateBadge />
        <span class="sub mono">SSN / SAREF4INMA</span>
      </div>
    </header>
    <div v-if="loading" class="skeleton"></div>
    <div v-else-if="error" class="err">{{ error }}</div>
    <div v-show="!loading && !error" ref="el" class="canvas"></div>
  </div>
</template>

<style scoped>
.kg {
  padding: var(--pad);
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 6px;
}
h3 {
  margin: 0;
  font-size: var(--fs-md);
  color: var(--semantic);
}
.sub {
  font-size: var(--fs-xs);
  color: var(--text-faint);
  letter-spacing: 0.08em;
}
.canvas {
  width: 100%;
  height: 460px;
}
.meta {
  display: flex;
  align-items: center;
  gap: 12px;
}
.err {
  color: var(--danger);
  font-size: var(--fs-sm);
  padding: 24px 0;
}
.skeleton {
  height: 460px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.55;
  }
}
</style>
