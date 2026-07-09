<script setup lang="ts">
// Right-side sliding drawer showing a device's recent records. Fetches via
// fetchDeviceData when the deviceId changes. Reused by DashboardView (panel
// click) and DeviceManagerView (detail button); the latter also renders the
// extra meta/control slot content.
import { ref, watch } from 'vue'
import { fetchDeviceData, type SensorRecord } from '../api'
import { DEVICE_META, protoLabel } from '../deviceMeta'
import JsonViewer from './JsonViewer.vue'

const props = defineProps<{ deviceId: string | null; limit?: number }>()
const emit = defineEmits<{ close: [] }>()

const records = ref<SensorRecord[]>([])
const error = ref('')
const loading = ref(false)

watch(
  () => props.deviceId,
  async (id) => {
    if (!id) return
    loading.value = true
    error.value = ''
    try {
      records.value = await fetchDeviceData(id, props.limit ?? 5)
    } catch {
      error.value = '数据加载失败'
      records.value = []
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)
</script>

<template>
  <div v-if="deviceId" class="overlay" @click.self="emit('close')">
    <aside class="drawer">
      <header class="head">
        <div>
          <span class="dev">{{ deviceId }}</span>
          <span v-if="DEVICE_META[deviceId]" class="proto">
            {{ protoLabel(DEVICE_META[deviceId].protocol) }}
          </span>
        </div>
        <button class="x" @click="emit('close')">×</button>
      </header>

      <div v-if="DEVICE_META[deviceId]" class="meta">
        <div><span class="k">子系统</span>{{ DEVICE_META[deviceId].subsystem }}</div>
        <div><span class="k">接入方式</span>{{ DEVICE_META[deviceId].connectVia }}</div>
      </div>

      <slot />

      <h4>最近数据</h4>
      <div v-if="loading" class="hint">加载中...</div>
      <div v-else-if="error" class="hint err">{{ error }}</div>
      <div v-else-if="!records.length" class="hint">暂无数据</div>
      <JsonViewer v-else :value="records" />
    </aside>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 50;
  display: flex;
  justify-content: flex-end;
}
.drawer {
  width: 420px;
  max-width: 90vw;
  height: 100%;
  background: #1e293b;
  border-left: 1px solid #334155;
  padding: 16px;
  overflow-y: auto;
  box-sizing: border-box;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.dev {
  font-family: monospace;
  color: #7dd3fc;
  font-size: 1rem;
}
.proto {
  margin-left: 8px;
  color: #fbbf24;
  font-size: 0.72rem;
  text-transform: uppercase;
}
.x {
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 1.4rem;
  cursor: pointer;
  line-height: 1;
}
.meta {
  font-size: 0.8rem;
  color: #e2e8f0;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.meta .k {
  display: inline-block;
  width: 72px;
  color: #94a3b8;
}
h4 {
  color: #38bdf8;
  font-size: 0.85rem;
  margin: 12px 0 8px;
}
.hint {
  color: #64748b;
  font-size: 0.85rem;
  padding: 12px 0;
}
.hint.err {
  color: #ef4444;
}
</style>
