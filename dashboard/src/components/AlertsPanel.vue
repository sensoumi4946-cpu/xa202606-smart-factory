<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchAlerts, type AlertItem } from '../api'

const alerts = ref<AlertItem[]>([])
const error = ref('')
const filterLevel = ref('')
let timer: ReturnType<typeof setInterval> | undefined

const filtered = computed(() => {
  if (!filterLevel.value) return alerts.value
  return alerts.value.filter((a) => a.level === filterLevel.value)
})

async function refresh() {
  try {
    const data = await fetchAlerts({ limit: 20 })
    alerts.value = data.items
  } catch {
    error.value = 'Fetch failed'
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 3000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="panel">
    <h3>告警面板</h3>
    <select v-model="filterLevel" class="filter">
      <option value="">All</option>
      <option value="warning">Warning</option>
      <option value="critical">Critical</option>
    </select>
    <div v-if="error" class="err">{{ error }}</div>
    <div v-if="!filtered.length" class="empty">No alerts</div>
    <div v-for="a in filtered" :key="a.id" class="alert-row" :class="a.level">
      <span class="level-badge" :class="a.level">{{ a.level }}</span>
      <span class="msg">{{ a.message }}</span>
      <span class="time">{{ new Date(a.triggered_at).toLocaleTimeString() }}</span>
    </div>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 8px; }
.filter { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; padding: 2px 6px; border-radius: 4px; margin-bottom: 8px; }
.alert-row { display: flex; gap: 8px; align-items: center; padding: 6px 8px; font-size: 0.8rem; border-radius: 4px; margin-bottom: 4px; }
.alert-row.warning { background: #78350f; }
.alert-row.critical { background: #7f1d1d; animation: blink 1s infinite; }
.level-badge { padding: 1px 6px; border-radius: 3px; font-weight: 600; text-transform: uppercase; font-size: 0.7rem; }
.level-badge.warning { background: #fbbf24; color: #1e293b; }
.level-badge.critical { background: #ef4444; color: #fff; }
.msg { flex: 1; color: #e2e8f0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.time { color: #94a3b8; white-space: nowrap; }
.empty { color: #64748b; padding: 12px 0; }
.err { color: #ef4444; font-size: 0.8rem; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
</style>
