<script setup lang="ts">
import { computed } from 'vue'
import { usePoll } from '../usePoll'
import {
  fetchLatestDeduped,
  fetchAlerts,
  fetchDevices,
  probeFuseki,
  type LatestDevice,
} from '../api'
import { FRESH_MS } from '../constants'

function isFresh(ts: string | undefined): boolean {
  if (!ts) return false
  return Date.now() - new Date(ts).getTime() < FRESH_MS
}

const { data: latest } = usePoll<LatestDevice[]>(
  'latest:deduped',
  fetchLatestDeduped,
  3000,
)

const { data: alerts } = usePoll<{ total: number }>(
  'alerts:count',
  () => fetchAlerts({ limit: 1 }),
  3000,
)

const { data: fuseki } = usePoll<boolean>('fuseki', probeFuseki, 10000)

const { data: devices } = usePoll<string[]>('devices', fetchDevices, 10000)

const liveProtocols = computed(() => {
  const set = new Set<string>()
  for (const d of latest.value ?? []) {
    if (d.measurements.some((m) => isFresh(m.timestamp))) {
      const p = (d as LatestDevice & { protocol?: string }).protocol
      if (p) set.add(p.toLowerCase())
    }
  }
  return set
})

const mqttOn = computed(() => liveProtocols.value.has('mqtt'))
const restOn = computed(() => liveProtocols.value.has('rest'))
const modbusOn = computed(() => liveProtocols.value.has('modbus'))
const opcuaOn = computed(() => liveProtocols.value.has('opcua'))
const fusekiOn = computed(() => fuseki.value === true)

const deviceCount = computed(() => (devices.value ?? []).length)
const alertCount = computed(() => alerts.value?.total ?? 0)
</script>

<template>
  <footer class="status-bar">
    <div class="lamps">
      <span class="lamp"><i :class="{ on: mqttOn }"></i>MQTT</span>
      <span class="lamp"><i :class="{ on: restOn }"></i>REST</span>
      <span class="lamp"><i :class="{ on: modbusOn }"></i>Modbus</span>
      <span class="lamp"><i :class="{ on: opcuaOn }"></i>OPC UA</span>
      <span class="lamp"><i :class="{ on: fusekiOn }"></i>Fuseki</span>
    </div>
    <div class="counts">
      <span>backend :8000</span>
      <span>{{ deviceCount }} devices</span>
      <span class="alerts" :class="{ zero: alertCount === 0 }">
        {{ alertCount }} alerts
      </span>
    </div>
  </footer>
</template>

<style scoped>
.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 6px 16px;
  background: var(--surface);
  border-top: 1px solid var(--line);
  font-size: 0.78rem;
  color: var(--text-faint);
  flex-wrap: wrap;
}
.lamps {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.lamp {
  display: flex;
  align-items: center;
  gap: 5px;
}
.lamp i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--line-strong);
  display: inline-block;
}
.lamp i.on {
  background: #34d399;
}
.counts {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.alerts {
  color: #fbbf24;
}
.zero {
  color: var(--text-faint) !important;
}
</style>
