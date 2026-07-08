<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchSemanticView, type SemanticSensor } from '../api'

const rows = ref<SemanticSensor[]>([])
const desc = ref('')
const error = ref('')
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const data = await fetchSemanticView('sensor-observations')
    rows.value = data.results
    desc.value = data.description
    error.value = ''
  } catch {
    error.value = '语义服务不可用'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="panel">
    <h3>语义关联: 传感器与观测属性</h3>
    <div v-if="loading" class="skeleton"></div>
    <div v-else-if="error" class="hint err">{{ error }}</div>
    <div v-else-if="!rows.length" class="hint">暂无语义数据</div>
    <table v-else>
      <thead>
        <tr><th>传感器</th><th>子系统</th><th>观测属性</th><th>协议</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.sensor">
          <td class="sensor">{{ r.sensor }}</td>
          <td><span class="tag">{{ r.subsystem }}</span></td>
          <td>{{ r.observes.join(', ') }}</td>
          <td class="proto">{{ r.protocol }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.panel { background: #1e293b; border-radius: 8px; padding: 12px; }
h3 { color: #38bdf8; font-size: 0.95rem; margin: 0 0 8px; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th, td { padding: 5px 8px; text-align: left; border-bottom: 1px solid #334155; color: #e2e8f0; }
th { color: #94a3b8; font-weight: 600; }
.sensor { font-family: monospace; color: #7dd3fc; }
.tag { background: #0f172a; border: 1px solid #334155; border-radius: 3px; padding: 1px 6px; color: #a5b4fc; }
.proto { color: #fbbf24; text-transform: uppercase; font-size: 0.72rem; }
.hint { color: #64748b; padding: 12px 0; font-size: 0.85rem; }
.hint.err { color: #ef4444; }
.skeleton { width: 100%; height: 96px; border-radius: 6px; background: #334155; animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.8; } }
</style>
