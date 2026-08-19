<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import {
  fetchLatestDeduped,
  rawRequest,
  type LatestDevice,
} from '../api'
import {
  DEVICE_META,
  protoLabel,
  subsystemLabel,
  refreshDeviceMeta,
} from '../deviceMeta'
import { FRESH_MS } from '../constants'
import DeviceDrawer from '../components/DeviceDrawer.vue'

const latest = ref<LatestDevice[]>([])
const error = ref('')
const drawerDev = ref<string | null>(null)
const now = ref(Date.now())
const busy = ref<string | null>(null)
const controlMsg = ref('')
let tick: ReturnType<typeof setInterval> | undefined
let poll: ReturnType<typeof setInterval> | undefined

function freshness(ts: string | undefined): number | null {
  if (!ts) return null
  const t = new Date(ts).getTime()
  if (Number.isNaN(t)) return null
  return now.value - t
}

function isFresh(ts: string | undefined): boolean {
  const age = freshness(ts)
  return age !== null && age < FRESH_MS
}

function ageLabel(ms: number | null): string {
  if (ms === null) return '--'
  if (ms < 0) return '0s'
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s`
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`
  return `${Math.floor(ms / 3_600_000)}h`
}

const latestMap = computed(() => {
  const map = new Map<string, LatestDevice>()
  for (const d of latest.value) map.set(d.device_id, d)
  return map
})

// Drive the table from the registry, not from a separate device-id list.
// The registry is the only source that carries protocol and subsystem, so
// a device present in one list but not the other used to render as "--".
const rows = computed(() => {
  const ids = new Set<string>([
    ...Object.keys(DEVICE_META),
    ...latest.value.map((d) => d.device_id),
  ])
  return [...ids]
    .map((id) => {
      const meta = DEVICE_META[id]
      const dev = latestMap.value.get(id)
      const newest = dev
        ? dev.measurements.reduce<string | undefined>((acc, m) => {
            if (!acc) return m.timestamp
            return new Date(m.timestamp) > new Date(acc) ? m.timestamp : acc
          }, undefined)
        : meta?.lastSeen
      const age = freshness(newest)
      return {
        id,
        protocol: protoLabel(meta?.protocol),
        subsystem: subsystemLabel(meta?.subsystem),
        online: isFresh(newest),
        age: ageLabel(age),
        summary: dev
          ? dev.measurements.map((m) => `${m.type}=${m.value}`).join(', ')
          : '--',
      }
    })
    .sort((a, b) => a.subsystem.localeCompare(b.subsystem) || a.id.localeCompare(b.id))
})

const onlineCount = computed(() => rows.value.filter((r) => r.online).length)

async function sendControl(deviceId: string, action: string) {
  busy.value = `${deviceId}:${action}`
  controlMsg.value = ''
  try {
    const res = await rawRequest('POST', '/api/v1/control', {
      device_id: deviceId,
      action,
      subsystem: DEVICE_META[deviceId]?.subsystem ?? 'actuator',
    })
    const body = res.body as { command_id?: string; status?: string } | null
    controlMsg.value = res.ok
      ? `已下发 ${action} · ${body?.status ?? ''} · ${body?.command_id?.slice(0, 8) ?? ''}`
      : `下发失败 HTTP ${res.status}`
  } catch {
    controlMsg.value = '下发失败：无法连接后端'
  } finally {
    busy.value = null
  }
}

async function load() {
  try {
    const [l] = await Promise.all([fetchLatestDeduped(), refreshDeviceMeta()])
    latest.value = l
    error.value = ''
  } catch {
    error.value = '设备列表加载失败'
  }
}

onMounted(() => {
  load()
  tick = setInterval(() => (now.value = Date.now()), 1000)
  poll = setInterval(load, 5000)
})
onUnmounted(() => {
  if (tick) clearInterval(tick)
  if (poll) clearInterval(poll)
})
</script>

<template>
  <div class="dm">
    <div v-if="error" class="err">{{ error }}</div>
    <div class="bar">
      <span class="count">{{ onlineCount }} / {{ rows.length }} 在线</span>
      <span v-if="controlMsg" class="ctrl-msg">{{ controlMsg }}</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>名称</th>
          <th>子系统</th>
          <th>协议</th>
          <th>状态</th>
          <th>最近数据</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td class="dev">{{ r.id }}</td>
          <td class="sub">{{ r.subsystem }}</td>
          <td class="proto">{{ r.protocol }}</td>
          <td>
            <span class="dot" :class="{ on: r.online }"></span>
            {{ r.online ? '在线' : '离线' }}
            <span class="age">{{ r.age }}</span>
          </td>
          <td class="summary">{{ r.summary }}</td>
          <td class="ops">
            <button
              class="op on"
              :disabled="busy === `${r.id}:on`"
              @click="sendControl(r.id, 'on')"
            >开启</button>
            <button
              class="op off"
              :disabled="busy === `${r.id}:off`"
              @click="sendControl(r.id, 'off')"
            >关闭</button>
            <button class="detail" @click="drawerDev = r.id">详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="6" class="empty">暂无设备</td>
        </tr>
      </tbody>
    </table>

    <DeviceDrawer :device-id="drawerDev" @close="drawerDev = null" />
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

.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 0.78rem;
}
.count { color: #94a3b8; }
.ctrl-msg { color: #34d399; font-family: monospace; font-size: 0.74rem; }
.sub { color: #cbd5e1; font-size: 0.78rem; }
.age { color: #64748b; font-size: 0.7rem; margin-left: 6px; }
.ops { display: flex; gap: 6px; }
.op {
  border: none;
  padding: 4px 12px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.78rem;
  color: #0f172a;
}
.op.on { background: #34d399; }
.op.off { background: #f87171; }
.op:disabled { opacity: 0.45; cursor: wait; }
</style>