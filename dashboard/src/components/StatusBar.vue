<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchLatestDeduped, fetchAlerts, fetchDevices, probeFuseki } from '../api'
import { FRESH_MS } from '../constants'

const mqttOn = ref(false)
const restOn = ref(false)
const modbusOn = ref(false)
const opcuaOn = ref(false)
const fusekiOn = ref(false)
const deviceCount = ref(0)
const alertCount = ref(0)

let fastTimer: ReturnType<typeof setInterval> | undefined
let slowTimer: ReturnType<typeof setInterval> | undefined

// A device is "fresh" if any measurement timestamp is within FRESH_MS.
function isFresh(ts: string | undefined): boolean {
  if (!ts) return false
  return Date.now() - new Date(ts).getTime() < FRESH_MS
}

async function refreshFast() {
  try {
    const latest = await fetchLatestDeduped()
    const freshIds = new Set(
      latest
        .filter((d) => d.measurements.some((m) => isFresh(m.timestamp)))
        .map((d) => d.device_id),
    )
    mqttOn.value = freshIds.has('sensor_dht22_01')
    restOn.value = freshIds.has('sensor_pir_01') || freshIds.has('sensor_ir_01')
    modbusOn.value = freshIds.has('sensor_mq2_01')
    opcuaOn.value = freshIds.has('sensor_hcsr04_01')
  } catch {
    mqttOn.value = restOn.value = modbusOn.value = opcuaOn.value = false
  }
  try {
    const alerts = await fetchAlerts({ limit: 1 })
    alertCount.value = alerts.total
  } catch {
    alertCount.value = 0
  }
}

async function refreshSlow() {
  fusekiOn.value = await probeFuseki()
  try {
    const devices = await fetchDevices()
    deviceCount.value = devices.length
  } catch {
    deviceCount.value = 0
  }
}

onMounted(() => {
  refreshFast()
  refreshSlow()
  fastTimer = setInterval(refreshFast, 3000)
  slowTimer = setInterval(refreshSlow, 10000)
})

onUnmounted(() => {
  if (fastTimer) clearInterval(fastTimer)
  if (slowTimer) clearInterval(slowTimer)
})
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
      <span class="alerts">{{ alertCount }} alerts</span>
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
  background: #1e293b;
  border-top: 1px solid #334155;
  font-size: 0.78rem;
  color: #94a3b8;
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
  background: #475569;
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
</style>