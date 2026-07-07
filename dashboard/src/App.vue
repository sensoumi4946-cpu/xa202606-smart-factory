<script setup lang="ts">
import { ref } from 'vue'
import TempGauge from './components/TempGauge.vue'
import GasMonitor from './components/GasMonitor.vue'
import AgvTrack from './components/AgvTrack.vue'
import CountBar from './components/CountBar.vue'
import LightingPanel from './components/LightingPanel.vue'
import AlertsPanel from './components/AlertsPanel.vue'
import HistoryTable from './components/HistoryTable.vue'
import SemanticPanel from './components/SemanticPanel.vue'

const title = 'XA-202606 智慧工厂安全监控平台'
const error = ref('')
</script>

<template>
  <div class="app">
    <h1 class="title">{{ title }}</h1>

    <div v-if="error" class="error">{{ error }}</div>

    <div class="grid">
      <TempGauge />
      <GasMonitor />
      <AgvTrack />
      <LightingPanel />
      <CountBar />
      <HistoryTable />
    </div>

    <div class="alerts-section">
      <AlertsPanel />
    </div>

    <div class="semantic-section">
      <SemanticPanel />
    </div>
  </div>
</template>

<style>
body {
  margin: 0;
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: #0f172a;
  color: #e2e8f0;
}
.app {
  max-width: 1440px;
  margin: 0 auto;
  padding: 16px 24px;
}
.title {
  font-size: 1.3rem;
  color: #38bdf8;
  text-align: center;
  margin-bottom: 16px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}
.alerts-section {
  max-width: 600px;
}
.semantic-section {
  margin-top: 12px;
}
.error {
  background: #7f1d1d;
  color: #fca5a5;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  margin-bottom: 12px;
}

@media (max-width: 960px) {
  .grid {
    grid-template-columns: 1fr;
  }
  .alerts-section {
    max-width: 100%;
  }
}
</style>
