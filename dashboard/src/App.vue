<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchDevices, fetchDeviceData, type SensorRecord } from './api'

const title = 'XA-202606 Smart Factory Safety Monitoring & Control Platform'
const devices = ref<string[]>([])
const selectedDevice = ref('')
const records = ref<SensorRecord[]>([])
const rawJson = ref('')
const error = ref('')

async function loadDevices() {
  try {
    devices.value = await fetchDevices()
  } catch (e: any) {
    error.value = e.message
  }
}

async function loadData(deviceId: string) {
  try {
    records.value = await fetchDeviceData(deviceId)
    rawJson.value = JSON.stringify(records.value, null, 2)
  } catch (e: any) {
    error.value = e.message
  }
}

function onSelect(deviceId: string) {
  selectedDevice.value = deviceId
  if (deviceId) {
    loadData(deviceId)
  }
}

onMounted(loadDevices)
</script>

<template>
  <div class="app">
    <h1>{{ title }}</h1>

    <div v-if="error" class="error">{{ error }}</div>

    <div class="toolbar">
      <label>
        Device:
        <select v-model="selectedDevice" @change="onSelect(selectedDevice)">
          <option value="">-- select --</option>
          <option v-for="d in devices" :key="d" :value="d">{{ d }}</option>
        </select>
      </label>
      <button @click="loadDevices">Refresh Devices</button>
    </div>

    <div v-if="records.length" class="data-section">
      <h3>Latest Records ({{ records.length }})</h3>
      <pre>{{ rawJson }}</pre>
    </div>
    <div v-else class="empty">
      No data available. Start the mock generator and backend to see sensor readings.
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
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem;
}
h1 {
  font-size: 1.4rem;
  color: #38bdf8;
}
.toolbar {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin: 1rem 0;
}
.toolbar select {
  padding: 0.3rem 0.6rem;
  background: #1e293b;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 4px;
}
.toolbar button {
  padding: 0.3rem 0.8rem;
  background: #1e293b;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 4px;
  cursor: pointer;
}
.toolbar button:hover {
  background: #334155;
}
.data-section {
  margin-top: 1rem;
}
.data-section pre {
  background: #1e293b;
  padding: 1rem;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 0.85rem;
}
.error {
  background: #7f1d1d;
  color: #fca5a5;
  padding: 0.5rem 1rem;
  border-radius: 4px;
}
.empty {
  color: #64748b;
  margin-top: 2rem;
}
</style>
