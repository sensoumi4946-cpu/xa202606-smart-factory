<script setup lang="ts">
// Tab 1 — the story view. Reads top-to-bottom as:
//   1. SystemPulse   — is the factory safe right now?
//   2. CrossAlertBanner — if not, WHY (correlated causal chain)
//   3. Sensor grid   — live per-device detail (click for history)
//   4. KnowledgeGraph (full width, live) — the semantic structure
//   5. SparqlPanel + AlertsPanel — query the ontology & event log
import { ref } from 'vue'
import TempGauge from '../components/TempGauge.vue'
import GasMonitor from '../components/GasMonitor.vue'
import AgvTrack from '../components/AgvTrack.vue'
import CountBar from '../components/CountBar.vue'
import LightingPanel from '../components/LightingPanel.vue'
import AlertsPanel from '../components/AlertsPanel.vue'
import SparqlPanel from '../components/SparqlPanel.vue'
import DeviceCard from '../components/DeviceCard.vue'
import DeviceDrawer from '../components/DeviceDrawer.vue'
import SystemPulse from '../components/SystemPulse.vue'
import CrossAlertBanner from '../components/CrossAlertBanner.vue'
import KnowledgeGraph from '../components/KnowledgeGraph.vue'

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
    <SystemPulse />
    <CrossAlertBanner />

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

    <DeviceCard :clickable="false">
      <KnowledgeGraph />
    </DeviceCard>

    <div class="lower">
      <DeviceCard :clickable="false">
        <SparqlPanel />
      </DeviceCard>
      <DeviceCard :clickable="false">
        <AlertsPanel />
      </DeviceCard>
    </div>

    <DeviceDrawer :device-id="drawerDev" @close="drawerDev = null" />
  </div>
</template>

<style scoped>
.dash {
  display: flex;
  flex-direction: column;
  gap: var(--gap);
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--gap);
}
.lower {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: var(--gap);
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
