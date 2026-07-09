<script setup lang="ts">
// Tab 4: system status. Two summary cards (API health / data throughput)
// plus a recent-events timeline aggregated from /latest and /alerts. Message
// rate is derived from the delta between two /history total counts over the
// elapsed interval. Only shows data the backend actually provides.
import { ref, onMounted, onUnmounted } from 'vue'
import {
  fetchSystemStatus,
  fetchLatest,
  fetchAlerts,
  fetchHistory,
  type SystemStatus,
} from '../api'
import { DEVICE_META } from '../deviceMeta'

interface Event {
  time: string
  kind: string
  text: string
}

const status = ref<SystemStatus | null>(null)
const rate = ref<number | null>(null)
const events = ref<Event[]>([])
const error = ref('')

let lastTotal: number | null = null
let lastAt: number | null = null
let timer: ReturnType<typeof setInterval> | undefined

// Estimates messages per second from consecutive /history totals.
async function sampleRate() {
  try {
    const h = await fetchHistory({ limit: 1 })
    const now = Date.now()
    if (lastTotal !== null && lastAt !== null) {
      const dt = (now - lastAt) / 1000
      if (dt > 0) rate.value = Math.max(0, (h.total - lastTotal) / dt)
    }
    lastTotal = h.total
    lastAt = now
  } catch {
    /* leave rate as-is */
  }
}

// Builds a merged timeline: latest readings tagged by protocol plus alert
// triggers, sorted newest first and capped to a short list.
async function buildEvents() {
  try {
    const [latest, alerts] = await Promise.all([
      fetchLatest(),
      fetchAlerts({ limit: 5 }),
    ])
    const rows: Event[] = []
    for (const d of latest) {
      const m = d.measurements[0]
      if (!m) continue
      rows.push({
        time: m.timestamp,
        kind: DEVICE_META[d.device_id]?.protocol ?? 'data',
        text: `${d.device_id} ${m.type}=${m.value}`,
      })
    }
    for (const a of alerts.items) {
      rows.push({
        time: a.triggered_at,
        kind: 'alert',
        text: `${a.rule_name} triggered (${a.level})`,
      })
    }
    rows.sort((x, y) => new Date(y.time).getTime() - new Date(x.time).getTime())
    events.value = rows.slice(0, 8)
  } catch {
    /* keep previous events */
  }
}

async function refresh() {
  try {
    status.value = await fetchSystemStatus()
    error.value = ''
  } catch {
    error.value = '状态加载失败'
  }
  await Promise.all([sampleRate(), buildEvents()])
}

function fmt(ts: string): string {
  return new Date(ts).toLocaleTimeString()
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 5000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="sys">
    <div v-if="error" class="err">{{ error }}</div>

    <div class="cards">
      <div class="card">
        <h3>API 健康</h3>
        <div class="row">
          <span class="k">/health</span>
          <span :class="status?.healthOk ? 'ok' : 'bad'">
            {{ status?.healthOk ? 'ok' : 'down' }}
          </span>
        </div>
        <div class="row">
          <span class="k">Fuseki</span>
          <span :class="status?.fusekiOk ? 'ok' : 'bad'">
            {{ status?.fusekiOk ? 'online' : 'offline' }}
          </span>
        </div>
        <div class="row">
          <span class="k">设备</span>
          <span>{{ status?.deviceCount ?? 0 }} 已注册</span>
        </div>
      </div>

      <div class="card">
        <h3>数据吞吐</h3>
        <div class="row">
          <span class="k">今日消息</span>
          <span>{{ status?.todayCount?.toLocaleString() ?? 0 }}</span>
        </div>
        <div class="row">
          <span class="k">速率</span>
          <span>{{ rate === null ? '采样中...' : `~${rate.toFixed(1)} msg/s` }}</span>
        </div>
        <div class="row">
          <span class="k">告警</span>
          <span class="warn">{{ status?.alertTotal ?? 0 }}</span>
        </div>
      </div>
    </div>

    <div class="card timeline">
      <h3>最近事件</h3>
      <div v-if="!events.length" class="empty">暂无事件</div>
      <div v-for="(e, i) in events" :key="i" class="event">
        <span class="t">{{ fmt(e.time) }}</span>
        <span class="tag" :class="e.kind">{{ e.kind }}</span>
        <span class="txt">{{ e.text }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.card {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 16px;
}
h3 {
  color: #38bdf8;
  font-size: 0.9rem;
  margin: 0 0 12px;
}
.row {
  display: flex;
  justify-content: space-between;
  padding: 5px 0;
  font-size: 0.85rem;
  color: #e2e8f0;
}
.k {
  color: #94a3b8;
}
.ok {
  color: #34d399;
}
.bad {
  color: #ef4444;
}
.warn {
  color: #fbbf24;
}
.timeline .event {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 5px 0;
  font-size: 0.8rem;
  border-bottom: 1px solid #1e293b;
}
.t {
  color: #94a3b8;
  font-family: monospace;
  white-space: nowrap;
}
.tag {
  border-radius: 3px;
  padding: 1px 6px;
  font-size: 0.68rem;
  text-transform: uppercase;
  background: #0f172a;
  color: #67e8f9;
}
.tag.alert {
  background: #7f1d1d;
  color: #fca5a5;
}
.txt {
  color: #cbd5e1;
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty {
  color: #64748b;
  font-size: 0.85rem;
  padding: 12px 0;
}
.err {
  color: #ef4444;
  font-size: 0.85rem;
  margin-bottom: 10px;
}
@media (max-width: 700px) {
  .cards {
    grid-template-columns: 1fr;
  }
}
</style>
