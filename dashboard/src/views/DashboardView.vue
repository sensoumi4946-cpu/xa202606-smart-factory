<script setup lang="ts">
// Tab 1: migrates the original App.vue dashboard content into a dedicated
// view. Chart logic stays inside the existing panel components; this view
// wraps each panel in the shared DeviceCard (protocol badge + click) and
// opens a history drawer keyed to the panel's primary device.
import { ref } from 'vue'
import TempGauge from '../components/TempGauge.vue'
import GasMonitor from '../components/GasMonitor.vue'
import AgvTrack from '../components/AgvTrack.vue'
import CountBar from '../components/CountBar.vue'
import LightingPanel from '../components/LightingPanel.vue'
import AlertsPanel from '../components/AlertsPanel.vue'
import SemanticPanel from '../components/SemanticPanel.vue'
import DeviceCard from '../components/DeviceCard.vue'
import DeviceDrawer from '../components/DeviceDrawer.vue'

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
      <DeviceCard
        v-for="p in PANELS"
        :key="p.dev"
        :device-id="p.dev"
        :protocol="p.proto"
        @open="drawerDev = $event"
      >
        <component :is="p.comp" />
      </DeviceCard>
    </div>

    <div class="lower">
      <DeviceCard :clickable="false">
        <AlertsPanel />
      </DeviceCard>
      <DeviceCard :clickable="false">
        <SemanticPanel />
      </DeviceCard>
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
