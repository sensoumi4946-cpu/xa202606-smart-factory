<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { fetchLatestDeduped, rawRequest, type LatestDevice } from '../api'
import { DEVICE_META, protoLabel, subsystemLabel, refreshDeviceMeta } from '../deviceMeta'
import { useClock, ageMs, shortAge, uptimeLabel } from '../freshness'
import { FRESH_MS } from '../constants'
import DeviceDrawer from '../components/DeviceDrawer.vue'
import EmptyState from '../components/EmptyState.vue'

interface DeviceExtra {
  firmware?: string
  mac?: string
  first_seen?: string
  message_count?: number
}

const latest = ref<LatestDevice[]>([])
const extras = ref<Record<string, DeviceExtra>>({})
const error = ref('')
const drawerDev = ref<string | null>(null)
const busy = ref<string | null>(null)
const controlMsg = ref('')
const clock = useClock()

const search = ref('')
const subsystemFilter = ref('all')
const statusFilter = ref('all')
const sortKey = ref<'id' | 'subsystem' | 'protocol' | 'age' | 'messages'>('subsystem')
const sortAsc = ref(true)

let poll: ReturnType<typeof setInterval> | undefined

const latestMap = computed(() => {
  const map = new Map<string, LatestDevice>()
  for (const d of latest.value) map.set(d.device_id, d)
  return map
})

const rows = computed(() => {
  const ids = new Set<string>([
    ...Object.keys(DEVICE_META),
    ...latest.value.map((d) => d.device_id),
  ])
  return [...ids].map((id) => {
    const meta = DEVICE_META[id]
    const dev = latestMap.value.get(id)
    const extra = extras.value[id] ?? {}
    const newest = dev
      ? dev.measurements.reduce<string | undefined>((acc, m) => {
          if (!acc) return m.timestamp
          return new Date(m.timestamp) > new Date(acc) ? m.timestamp : acc
        }, undefined)
      : meta?.lastSeen
    const age = ageMs(newest, clock.value)
    return {
      id,
      protocol: protoLabel(meta?.protocol),
      protocolKey: meta?.protocol ?? '',
      subsystem: subsystemLabel(meta?.subsystem),
      subsystemKey: meta?.subsystem ?? '',
      online: age !== null && age < FRESH_MS,
      age,
      ageText: shortAge(age),
      firmware: extra.firmware ?? '--',
      mac: extra.mac ?? '--',
      uptime: uptimeLabel(extra.first_seen, clock.value),
      messages: extra.message_count ?? 0,
      summary: dev
        ? dev.measurements.map((m) => `${m.type}=${m.value}`).join('  ')
        : '--',
    }
  })
})

const subsystems = computed(() => {
  const set = new Set(rows.value.map((r) => r.subsystemKey).filter(Boolean))
  return [...set].sort()
})

const visible = computed(() => {
  const q = search.value.trim().toLowerCase()
  let out = rows.value.filter((r) => {
    if (q && !r.id.toLowerCase().includes(q) && !r.subsystem.includes(q)) return false
    if (subsystemFilter.value !== 'all' && r.subsystemKey !== subsystemFilter.value) return false
    if (statusFilter.value === 'online' && !r.online) return false
    if (statusFilter.value === 'offline' && r.online) return false
    return true
  })
  const dir = sortAsc.value ? 1 : -1
  out = [...out].sort((a, b) => {
    switch (sortKey.value) {
      case 'age':
        return ((a.age ?? Infinity) - (b.age ?? Infinity)) * dir
      case 'messages':
        return (a.messages - b.messages) * dir
      case 'protocol':
        return a.protocol.localeCompare(b.protocol) * dir
      case 'subsystem':
        return (a.subsystem.localeCompare(b.subsystem) || a.id.localeCompare(b.id)) * dir
      default:
        return a.id.localeCompare(b.id) * dir
    }
  })
  return out
})

const onlineCount = computed(() => rows.value.filter((r) => r.online).length)

function sortBy(key: typeof sortKey.value) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else {
    sortKey.value = key
    sortAsc.value = true
  }
}

function arrow(key: typeof sortKey.value): string {
  if (sortKey.value !== key) return ''
  return sortAsc.value ? ' ↑' : ' ↓'
}

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
      ? `${deviceId} ${action} 已下发 · ${body?.status ?? ''} · ${body?.command_id?.slice(0, 8) ?? ''}`
      : `下发失败 HTTP ${res.status}`
  } catch {
    controlMsg.value = '下发失败：无法连接后端'
  } finally {
    busy.value = null
  }
}

async function loadExtras() {
  try {
    const res = await rawRequest('GET', '/api/v1/devices/detail')
    if (!res.ok) return
    const body = res.body as { items?: (DeviceExtra & { device_id: string })[] } | null
    const map: Record<string, DeviceExtra> = {}
    for (const item of body?.items ?? []) map[item.device_id] = item
    extras.value = map
  } catch {
    // endpoint is optional; columns fall back to '--'
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
  loadExtras()
}

onMounted(() => {
  load()
  poll = setInterval(load, 5000)
})
onUnmounted(() => {
  if (poll) clearInterval(poll)
})
</script>

<template>
  <div class="dm">
    <header class="bar">
      <input v-model="search" class="search" type="search" placeholder="搜索设备号或子系统" />
      <select v-model="subsystemFilter" class="sel">
        <option value="all">全部子系统</option>
        <option v-for="s in subsystems" :key="s" :value="s">{{ subsystemLabel(s) }}</option>
      </select>
      <select v-model="statusFilter" class="sel">
        <option value="all">全部状态</option>
        <option value="online">仅在线</option>
        <option value="offline">仅离线</option>
      </select>
      <span class="count mono">{{ visible.length }} / {{ rows.length }} 台 · {{ onlineCount }} 在线</span>
      <span v-if="controlMsg" class="ctrl mono">{{ controlMsg }}</span>
    </header>

    <EmptyState
      v-if="error || !rows.length"
      :kind="error ? 'error' : 'empty'"
      :title="error ? '设备列表加载失败' : '暂无设备接入'"
      :detail="error ? '无法连接后端服务，请确认 backend 已在 8000 端口运行。' : '平台已就绪，等待设备上报数据。'"
      hint="curl http://localhost:8000/api/v1/devices"
      @retry="load"
    />

    <table v-else>
      <thead>
        <tr>
          <th class="s" @click="sortBy('id')">设备号{{ arrow('id') }}</th>
          <th class="s c-sub" @click="sortBy('subsystem')">子系统{{ arrow('subsystem') }}</th>
          <th class="s c-proto" @click="sortBy('protocol')">协议{{ arrow('protocol') }}</th>
          <th class="c-state">状态</th>
          <th class="s c-age" @click="sortBy('age')">最后上报{{ arrow('age') }}</th>
          <th class="c-fw">固件</th>
          <th class="c-mac">MAC</th>
          <th class="c-up">运行时长</th>
          <th class="s c-msg" @click="sortBy('messages')">报文数{{ arrow('messages') }}</th>
          <th>最近数据</th>
          <th class="c-ops">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in visible" :key="r.id" :class="{ off: !r.online }">
          <td class="mono dev">{{ r.id }}</td>
          <td class="c-sub">{{ r.subsystem }}</td>
          <td class="c-proto mono">{{ r.protocol }}</td>
          <td class="c-state">
            <span class="dot" :class="{ on: r.online }"></span>{{ r.online ? '在线' : '离线' }}
          </td>
          <td class="c-age mono">{{ r.ageText }}</td>
          <td class="c-fw mono">{{ r.firmware }}</td>
          <td class="c-mac mono">{{ r.mac }}</td>
          <td class="c-up mono">{{ r.uptime }}</td>
          <td class="c-msg mono">{{ r.messages || '--' }}</td>
          <td class="mono sum">{{ r.summary }}</td>
          <td class="c-ops">
            <button :disabled="busy === `${r.id}:on`" @click="sendControl(r.id, 'on')">开启</button>
            <button :disabled="busy === `${r.id}:off`" @click="sendControl(r.id, 'off')">关闭</button>
            <button @click="drawerDev = r.id">详情</button>
          </td>
        </tr>
        <tr v-if="!visible.length">
          <td colspan="11" class="empty">
            {{ rows.length ? '没有符合筛选条件的设备' : '暂无设备接入' }}
          </td>
        </tr>
      </tbody>
    </table>

    <DeviceDrawer :device-id="drawerDev" @close="drawerDev = null" />
  </div>
</template>

<style scoped>
.dm { padding: 12px 16px 20px; }
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.search, .sel {
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  color: var(--text);
  font-size: 12px;
  padding: 4px 8px;
}
.search { width: 220px; }
.count { font-size: 11px; color: var(--text-faint); margin-left: auto; }
.ctrl { font-size: 11px; color: var(--ok); }
.err { color: var(--danger); font-size: 12px; margin-bottom: 8px; }

table { width: 100%; border-collapse: collapse; font-size: 12px; }
th {
  text-align: left;
  font-weight: 500;
  font-size: 11px;
  color: var(--text-faint);
  padding: 5px 8px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
th.s { cursor: pointer; user-select: none; }
th.s:hover { color: var(--text); }
td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--line);
  color: var(--text-dim);
}
tr.off td { color: var(--text-faint); }
.dev { color: var(--text); }
.c-sub { width: 90px; }
.c-proto { width: 74px; }
.c-state { width: 74px; }
.c-age, .c-up, .c-msg { width: 78px; }
.c-fw { width: 78px; }
.c-mac { width: 130px; }
.c-ops { width: 150px; white-space: nowrap; }
.sum { color: var(--text-faint); }
.dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--line-strong);
  margin-right: 6px;
}
.dot.on { background: var(--ok); }
.c-ops button {
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  color: var(--text-dim);
  font-size: 11px;
  padding: 2px 8px;
  margin-right: 4px;
  cursor: pointer;
}
.c-ops button:hover { color: var(--text); }
.c-ops button:disabled { opacity: 0.4; cursor: wait; }
.empty { color: var(--text-faint); padding: 20px 8px; text-align: center; }
</style>
