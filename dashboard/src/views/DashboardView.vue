<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  devicesBySubsystem,
  measurementFor,
  useSubsystemDevices,
} from '../subsystemDevices'
import { useClock, ageMs } from '../freshness'
import PanelFrame from '../components/PanelFrame.vue'
import SensorGauge from '../components/SensorGauge.vue'
import GasMonitor from '../components/GasMonitor.vue'
import AlertsPanel from '../components/AlertsPanel.vue'
import SparqlPanel from '../components/SparqlPanel.vue'
import KnowledgeGraph from '../components/KnowledgeGraph.vue'
import CrossAlertBanner from '../components/CrossAlertBanner.vue'
import DeviceDrawer from '../components/DeviceDrawer.vue'
import EmptyState from '../components/EmptyState.vue'

useSubsystemDevices()
const devices = devicesBySubsystem()
const clock = useClock()
const drawerDev = ref<string | null>(null)

const anyData = computed(() =>
  Object.keys(devices.value ?? {}).length > 0,
)

function reload() {
  window.location.reload()
}

function reading(subsystem: string, type: string) {
  return measurementFor(subsystem, type)
}

function protoOf(subsystem: string): string {
  return devices.value[subsystem]?.protocol ?? ''
}

function tsOf(subsystem: string, type: string): string | null {
  return reading(subsystem, type)?.timestamp ?? null
}

function level(
  value: number | null,
  warn: number,
  danger: number,
  direction: 'high' | 'low' = 'high',
): 'ok' | 'warn' | 'danger' | 'idle' {
  if (value === null) return 'idle'
  if (direction === 'high') {
    if (value >= danger) return 'danger'
    if (value >= warn) return 'warn'
  } else {
    if (value <= danger) return 'danger'
    if (value <= warn) return 'warn'
  }
  return 'ok'
}

const temp = computed(() => reading('temp_humidity', 'temperature')?.value ?? null)
const humidity = computed(() => reading('temp_humidity', 'humidity')?.value ?? null)
const distance = computed(() => reading('agv', 'distance')?.value ?? null)
const count = computed(() => reading('counting', 'count')?.value ?? null)
const occupancy = computed(() => reading('lighting', 'occupancy')?.value ?? null)
const lightState = computed(() => reading('lighting', 'light_state')?.value ?? null)

const tempState = computed(() => level(temp.value, 30, 38))
const distState = computed(() => level(distance.value, 30, 15, 'low'))

const countAge = computed(() => ageMs(tsOf('counting', 'count'), clock.value))
const countRate = computed(() => {
  if (count.value === null || countAge.value === null) return null
  return countAge.value < 60_000 ? count.value : null
})
</script>

<template>
  <EmptyState
    v-if="!anyData"
    kind="offline"
    title="未检测到任何设备接入"
    detail="平台已启动，但尚未收到传感器数据。请确认后端服务、MQTT broker 与设备侧程序均在运行。"
    hint="curl http://localhost:8000/api/v1/devices"
    @retry="reload"
  />

  <div v-else class="grid">
    <div class="banner">
      <CrossAlertBanner />
    </div>

    <PanelFrame
      class="p-temp"
      title="温湿度"
      :protocol="protoOf('temp_humidity')"
      :timestamp="tsOf('temp_humidity', 'temperature')"
      :state="tempState"
    >
      <div class="gauges">
        <SensorGauge
          label="温度"
          :value="temp"
          unit="°C"
          :min="0"
          :max="60"
          :warn="30"
          :danger="38"
          :size="132"
        />
        <SensorGauge
          label="湿度"
          :value="humidity"
          unit="%"
          :min="0"
          :max="100"
          :warn="80"
          :danger="90"
          :size="132"
        />
      </div>
    </PanelFrame>

    <PanelFrame
      class="p-gas"
      title="危险气体"
      :protocol="protoOf('gas')"
      :timestamp="tsOf('gas', 'co')"
      :state="level(reading('gas', 'co')?.value ?? null, 20, 35)"
    >
      <GasMonitor />
    </PanelFrame>

    <PanelFrame
      class="p-agv"
      title="AGV 避障距离"
      :protocol="protoOf('agv')"
      :timestamp="tsOf('agv', 'distance')"
      :state="distState"
    >
      <div class="gauges">
        <SensorGauge
          label="最近障碍物"
          :value="distance"
          unit="cm"
          :min="0"
          :max="200"
          :warn="30"
          :danger="15"
          direction="low"
          :size="140"
        />
      </div>
      <p class="hint">数值越小越危险；橙色为减速区，红色为停车区。</p>
    </PanelFrame>

    <PanelFrame
      class="p-light"
      title="红外感应照明"
      :protocol="protoOf('lighting')"
      :timestamp="tsOf('lighting', 'occupancy')"
      dense
    >
      <dl class="kv">
        <dt>人员</dt>
        <dd :class="{ active: occupancy === 1 }">
          {{ occupancy === null ? '--' : occupancy === 1 ? '有人' : '无人' }}
        </dd>
        <dt>照明</dt>
        <dd :class="{ active: lightState === 1 }">
          {{ lightState === null ? '--' : lightState === 1 ? '开' : '关' }}
        </dd>
      </dl>
    </PanelFrame>

    <PanelFrame
      class="p-count"
      title="货物计数"
      :protocol="protoOf('counting')"
      :timestamp="tsOf('counting', 'count')"
      dense
    >
      <div class="big mono">{{ count === null ? '--' : Math.round(count) }}</div>
      <div class="big-unit">件 · 累计</div>
      <div v-if="countRate === null" class="hint">暂无近期数据</div>
    </PanelFrame>

    <PanelFrame class="p-alerts" title="实时告警">
      <AlertsPanel />
    </PanelFrame>

    <PanelFrame class="p-kg" title="知识图谱">
      <KnowledgeGraph />
    </PanelFrame>

    <PanelFrame class="p-sparql" title="语义查询" dense>
      <SparqlPanel />
    </PanelFrame>

    <DeviceDrawer :device-id="drawerDev" @close="drawerDev = null" />
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-auto-rows: min-content;
  gap: 10px;
  padding: 12px 16px 20px;
  align-items: stretch;
}

.banner { grid-column: 1 / -1; }

.p-temp { grid-column: span 3; }
.p-gas { grid-column: span 6; grid-row: span 3; }
.p-agv { grid-column: span 3; grid-row: span 3; }
.p-light { grid-column: span 3; }
.p-count { grid-column: span 3; }
.p-alerts { grid-column: span 3; grid-row: span 2; }
.p-kg { grid-column: span 5; grid-row: span 2; }
.p-sparql { grid-column: span 4; grid-row: span 2; }

.gauges {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  height: 100%;
  min-height: 0;
}

.kv {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 16px;
  margin: 0;
  font-size: 13px;
}
.kv dt { color: var(--text-dim); }
.kv dd { margin: 0; color: var(--text-faint); }
.kv dd.active { color: var(--ok); }

.big {
  font-size: 40px;
  line-height: 1.1;
  font-weight: 600;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.big-unit {
  font-size: 11px;
  color: var(--text-faint);
  margin-top: 2px;
}
.hint {
  margin: 6px 0 0;
  font-size: 10px;
  color: var(--text-faint);
  line-height: 1.5;
}

@media (max-width: 1280px) {
  .p-temp, .p-light, .p-count, .p-alerts { grid-column: span 6; }
  .p-gas, .p-kg, .p-sparql { grid-column: span 12; }
  .p-agv { grid-column: span 6; }
}
</style>
