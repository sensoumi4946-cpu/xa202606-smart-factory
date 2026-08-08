<script setup lang="ts">
// Tab 3: device manager. Lists known devices from /api/v1/devices sorted by
// subsystem, joins each with DEVICE_META for protocol and access path, and
// infers online state from 30s data freshness in /latest. A detail button
// opens DeviceDrawer showing the last five records plus a simulated remote
// control section.
import { ref, onMounted, computed } from 'vue'
import { fetchDevices, fetchLatestDeduped, type LatestDevice } from '../api'
import { DEVICE_META, protoLabel } from '../deviceMeta'
import DeviceDrawer from '../components/DeviceDrawer.vue'

const FRESH_MS = 120_000

const ids = ref<string[]>([])
const latest = ref<LatestDevice[]>([])
const error = ref('')
const drawerDev = ref<string | null>(null)

function isFresh(ts: string | undefined): boolean {
  if (!ts) return false
  return Date.now() - new Date(ts).getTime() < FRESH_MS
}

// O(1) lookup: index latest by device_id once.
const latestMap = computed(() => {
  const map = new Map<string, LatestDevice>()
  for (const d of latest.value) map.set(d.device_id, d)
  return map
})

// IDs pre-sorted once; only re-computes when ids changes.
const sortedIds = computed(() =>
  [...ids.value].sort((a, b) => {
    const sa = DEVICE_META[a]?.subsystem ?? ''
    const sb = DEVICE_META[b]?.subsystem ?? ''
    return sa.localeCompare(sb)
  }),
)

const rows = computed(() =>
  sortedIds.value.map((id) => {
    const dev = latestMap.value.get(id)
    const online = !!dev && dev.measurements.some((m) => isFresh(m.timestamp))
    const summary = dev
      ? dev.measurements.map((m) => `${m.type}=${m.value}`).join(', ')
      : '--'
    return { id, meta: DEVICE_META[id], online, summary }
  }),
)

async function load() {
  try {
    const [d, l] = await Promise.all([fetchDevices(), fetchLatestDeduped()])
    ids.value = d
    latest.value = l
    error.value = ''
  } catch {
    error.value = '设备列表加载失败'
  }
}

onMounted(load)
</script>

<template>
  <div class="dm">
    <div v-if="error" class="err">{{ error }}</div>
    <table>
      <thead>
        <tr>
          <th>名称</th>
          <th>协议</th>
          <th>状态</th>
          <th>最近数据</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td class="dev">{{ r.id }}</td>
          <td class="proto">{{ r.meta ? protoLabel(r.meta.protocol) : '--' }}</td>
          <td>
            <span class="dot" :class="{ on: r.online }"></span>
            {{ r.online ? '在线' : '离线' }}
          </td>
          <td class="summary">{{ r.summary }}</td>
          <td>
            <button class="detail" @click="drawerDev = r.id">详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="5" class="empty">暂无设备</td>
        </tr>
      </tbody>
    </table>

    <DeviceDrawer :device-id="drawerDev" @close="drawerDev = null">
      <div class="control">
        <h4>远程控制 <span class="sim">模拟模式</span></h4>
        <div class="btns">
          <button disabled>开启</button>
          <button disabled>关闭</button>
        </div>
        <div class="pending">
          <div><span class="k">固件版本</span>待上报</div>
          <div><span class="k">MAC 地址</span>待上报</div>
        </div>
      </div>
    </DeviceDrawer>
  </div>
</template>

<style scoped>
.dm {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 16px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
th,
td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid #334155;
  color: #e2e8f0;
}
th {
  color: #94a3b8;
  font-weight: 600;
}
.dev {
  font-family: monospace;
  color: #7dd3fc;
}
.proto {
  color: #fbbf24;
  text-transform: uppercase;
  font-size: 0.74rem;
}
.summary {
  color: #cbd5e1;
  font-family: monospace;
  font-size: 0.76rem;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #475569;
  display: inline-block;
  margin-right: 5px;
}
.dot.on {
  background: #34d399;
  box-shadow: 0 0 6px #34d399;
}
.detail {
  background: #334155;
  color: #e2e8f0;
  border: none;
  padding: 4px 12px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.78rem;
}
.detail:hover {
  background: #475569;
}
.empty {
  color: #64748b;
  text-align: center;
  padding: 20px;
}
.err {
  color: #ef4444;
  font-size: 0.85rem;
  margin-bottom: 10px;
}
.control {
  border-top: 1px solid #334155;
  margin-top: 12px;
  padding-top: 12px;
}
.control h4 {
  color: #38bdf8;
  font-size: 0.85rem;
  margin: 0 0 8px;
}
.sim {
  color: #94a3b8;
  font-size: 0.7rem;
  font-weight: 400;
}
.btns {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.btns button {
  background: #334155;
  color: #64748b;
  border: none;
  padding: 6px 18px;
  border-radius: 6px;
  cursor: not-allowed;
  font-size: 0.8rem;
}
.pending {
  font-size: 0.78rem;
  color: #94a3b8;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.pending .k {
  display: inline-block;
  width: 72px;
  color: #64748b;
}
</style>
