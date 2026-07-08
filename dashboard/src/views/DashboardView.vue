<script setup lang="ts">
// Tab 1: migrates the original App.vue dashboard content into a dedicated
// view. Chart logic stays inside the existing panel components; this view
// only adds unified cards, a protocol badge per panel and a click-to-open
// history drawer keyed to the panel's primary device.
import { ref } from 'vue'
import TempGauge from '../components/TempGauge.vue'
import GasMonitor from '../components/GasMonitor.vue'
import AgvTrack from '../components/AgvTrack.vue'
import CountBar from '../components/CountBar.vue'
import LightingPanel from '../components/LightingPanel.vue'
import AlertsPanel from '../components/AlertsPanel.vue'
import SemanticPanel from '../components/SemanticPanel.vue'
import DeviceDrawer from '../components/DeviceDrawer.vue'
import { protoLabel } from '../deviceMeta'

// Panel -> primary device id + component, so a card click can open history.
const PANELS = [
  { dev: 'sensor_dht22_01', proto: 'mqtt', comp: TempGauge },
  { dev: 'sensor_mq2_01', proto: 'modbus', comp: GasMonitor },
  { dev: 'sensor_hcsr04_01', proto: 'opcua', comp: AgvTrack },
  { dev: 'sensor_pir_01', proto: 'rest', comp: LightingPanel },
  { dev: 'sensor_ir_01', proto: 'rest', comp: CountBar },
]

const drawerDev = ref<string | null>(null)
</script>

<template>
  <div class="dash">
    <div class="grid">
      <div
        v-for="p in PANELS"
        :key="p.dev"
        class="card"
        @click="drawerDev = p.dev"
      >
        <span class="badge">{{ protoLabel(p.proto) }}</span>
        <component :is="p.comp" />
      </div>
    </div>

    <div class="lower">
      <div class="card wide">
        <AlertsPanel />
      </div>
      <div class="card wide">
        <SemanticPanel />
      </div>
    </div>

    <DeviceDrawer :device-id="drawerDev" @close="drawerDev = null" />
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}
.lower {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.card {
  position: relative;
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 4px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.card:hover {
  border-color: #38bdf8;
}
.card.wide {
  cursor: default;
}
.badge {
  position: absolute;
  top: 8px;
  right: 10px;
  z-index: 2;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 0.66rem;
  color: #fbbf24;
  text-transform: uppercase;
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .lower {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 600px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
