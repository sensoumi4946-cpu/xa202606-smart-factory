<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchDevices, fetchHistory, type SensorRecord } from '../api'

const devices = ref<string[]>([])
const selDevice = ref('')
const since = ref('')
const until = ref('')
const items = ref<SensorRecord[]>([])
const total = ref(0)
const page = ref(0)
const limit = 10
const error = ref('')

async function loadDevices() {
  try { devices.value = await fetchDevices() } catch (e: any) { error.value = e.message }
}
async function search() {
  try {
    const params: Record<string, any> = { limit, offset: page.value * limit }
    if (selDevice.value) params.device_id = selDevice.value
    if (since.value) params.since = new Date(since.value).toISOString()
    if (until.value) params.until = new Date(until.value).toISOString()
    const data = await fetchHistory(params)
    items.value = data.items
    total.value = data.total
    error.value = ''
  } catch (e: any) { error.value = e.message }
}
function prevPage() { if (page.value > 0) { page.value--; search() } }
function nextPage() { if ((page.value + 1) * limit < total.value) { page.value++; search() } }

onMounted(loadDevices)
</script>

<template>
  <div class="panel">
    <h3>历史查询</h3>
    <div class="controls">
      <select v-model="selDevice"><option value="">All devices</option><option v-for="d in devices" :key="d" :value="d">{{ d }}</option></select>
      <input type="datetime-local" v-model="since" />
      <input type="datetime-local" v-model="until" />
      <button @click="search">Search</button>
    </div>
    <div v-if="error" class="err">{{ error }}</div>
    <div v-if="!items.length" class="empty">No data. Select filters and click Search.</div>
    <table v-else>
      <thead><tr><th>Time</th><th>Device</th><th>Type</th><th>Value</th></tr></thead>
      <tbody>
        <tr v-for="r in items" :key="r.id">
          <td>{{ new Date(r.timestamp).toLocaleString() }}</td>
          <td>{{ r.device_id }}</td>
          <td>{{ r.measurements.map(m => m.type).join(', ') }}</td>
          <td>{{ r.measurements.map(m => `${m.value} ${m.unit}`).join(', ') }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="items.length" class="pager">
      <button :disabled="page === 0" @click="prevPage">Prev</button>
      <span>{{ total }} total</span>
      <button :disabled="(page + 1) * limit >= total" @click="nextPage">Next</button>
    </div>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 8px; }
.controls { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; align-items: center; }
.controls select, .controls input { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; }
.controls button { background: #334155; color: #e2e8f0; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th, td { padding: 4px 6px; text-align: left; border-bottom: 1px solid #334155; color: #e2e8f0; }
th { color: #94a3b8; }
.pager { display: flex; gap: 8px; align-items: center; margin-top: 8px; font-size: 0.8rem; color: #e2e8f0; }
.pager button { background: #334155; color: #e2e8f0; border: none; padding: 2px 8px; border-radius: 4px; cursor: pointer; }
.pager button:disabled { opacity: 0.4; cursor: default; }
.empty { color: #64748b; padding: 12px 0; font-size: 0.85rem; }
.err { color: #ef4444; font-size: 0.8rem; margin-bottom: 4px; }
</style>
