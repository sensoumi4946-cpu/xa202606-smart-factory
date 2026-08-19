<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { rawRequest, fetchLatestDeduped, fetchAlerts, type AlertItem, type LatestDevice } from '../api'
import { DEVICE_META, protoLabel, refreshDeviceMeta } from '../deviceMeta'
import { FRESH_MS } from '../constants'
import KnowledgeGraph from '../components/KnowledgeGraph.vue'

const emit = defineEmits<{ exit: [] }>()

const latest = ref<LatestDevice[]>([])
const alerts = ref<AlertItem[]>([])
const hazards = ref<any[]>([])
const predictions = ref<any[]>([])
const agv = ref<any[]>([])
const clock = ref('')
const now = ref(Date.now())
const connected = ref(true)

let poll: ReturnType<typeof setInterval> | undefined
let tick: ReturnType<typeof setInterval> | undefined

const SUBSYSTEMS = [
  { key: 'temp_humidity', label: '温湿度监控', props: ['temperature', 'humidity'], units: ['°C', '%'] },
  { key: 'lighting', label: '红外感应照明', props: ['occupancy', 'light_state'], units: ['', ''] },
  { key: 'gas', label: '危险气体监测', props: ['co', 'smoke'], units: ['ppm', 'ppm'] },
  { key: 'agv', label: 'AGV 避障', props: ['distance'], units: ['cm'] },
  { key: 'counting', label: '货物感应计数', props: ['count'], units: ['件'] },
]

function valueOf(subsystem: string, prop: string): { v: number | null; ts: string | null } {
  for (const d of latest.value) {
    const meta = DEVICE_META[d.device_id]
    const sub = meta?.subsystem ?? d.subsystem
    if (sub !== subsystem) continue
    const m = d.measurements.find((x) => x.type === prop)
    if (m) return { v: m.value, ts: m.timestamp }
  }
  return { v: null, ts: null }
}

function fmt(v: number | null, prop: string): string {
  if (v === null) return '--'
  if (prop === 'occupancy') return v > 0.5 ? '有人' : '无人'
  if (prop === 'light_state') return v > 0.5 ? '开' : '关'
  if (prop === 'count') return String(Math.round(v))
  return v.toFixed(1)
}

const tiles = computed(() =>
  SUBSYSTEMS.map((s) => {
    const readings = s.props.map((p, i) => {
      const { v, ts } = valueOf(s.key, p)
      return { prop: p, text: fmt(v, p), unit: s.units[i], ts }
    })
    const freshest = readings
      .map((r) => (r.ts ? now.value - new Date(r.ts).getTime() : Infinity))
      .sort((a, b) => a - b)[0]
    const online = freshest < FRESH_MS
    const device = latest.value.find(
      (d) => (DEVICE_META[d.device_id]?.subsystem ?? d.subsystem) === s.key,
    )
    const proto = device ? protoLabel(DEVICE_META[device.device_id]?.protocol) : '--'
    const alarming = alerts.value.some(
      (a) => a.subsystem === s.key && now.value - new Date(a.triggered_at).getTime() < 30_000,
    )
    return { ...s, readings, online, proto, alarming }
  }),
)

const criticalHazard = computed(() => hazards.value[0] ?? null)

const kpis = computed(() => {
  const online = tiles.value.filter((t) => t.online).length
  const protos = new Set(
    latest.value.map((d) => DEVICE_META[d.device_id]?.protocol).filter(Boolean),
  )
  const critical = alerts.value.filter((a) => a.level === 'critical').length
  const soonest = predictions.value[0]
  return {
    online,
    total: SUBSYSTEMS.length,
    protocols: protos.size,
    critical,
    prediction: soonest
      ? `${soonest.property_name} ${Math.round(soonest.seconds_to_threshold)}s`
      : '正常',
  }
})

const ticker = computed(() => alerts.value.slice(0, 12))

function timeOf(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '--' : d.toLocaleTimeString()
}

async function safeGet(path: string): Promise<any[]> {
  try {
    const res = await rawRequest('GET', path)
    if (!res.ok) return []
    const body = res.body as { items?: any[] } | null
    return body?.items ?? []
  } catch {
    return []
  }
}

async function load() {
  try {
    const [l, a] = await Promise.all([
      fetchLatestDeduped(),
      fetchAlerts({ limit: 20 }),
    ])
    latest.value = l
    alerts.value = a.items
    connected.value = true
  } catch {
    connected.value = false
  }
  const [h, p, g] = await Promise.all([
    safeGet('/api/v1/hazards?limit=5'),
    safeGet('/api/v1/predictions'),
    safeGet('/api/v1/agv'),
  ])
  hazards.value = h
  predictions.value = p
  agv.value = g
  refreshDeviceMeta()
}

onMounted(() => {
  load()
  poll = setInterval(load, 2000)
  tick = setInterval(() => {
    now.value = Date.now()
    clock.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  }, 1000)
})
onUnmounted(() => {
  if (poll) clearInterval(poll)
  if (tick) clearInterval(tick)
})
</script>

<template>
  <div class="wall">
    <header class="wall-head">
      <div class="left">
        <span class="mark"></span>
        <span class="code">XA-202606</span>
        <h1>智慧工厂安全监测控制平台</h1>
      </div>
      <div class="right">
        <span class="os">国产操作系统 openEuler 部署</span>
        <span class="clock">{{ clock }}</span>
        <button class="exit" @click="emit('exit')">退出大屏 (Esc)</button>
      </div>
    </header>

    <section class="kpis">
      <div class="kpi">
        <span class="k-val">{{ kpis.online }}/{{ kpis.total }}</span>
        <span class="k-lab">子系统在线</span>
      </div>
      <div class="kpi">
        <span class="k-val">{{ kpis.protocols }}</span>
        <span class="k-lab">异构协议接入</span>
      </div>
      <div class="kpi" :class="{ bad: kpis.critical > 0 }">
        <span class="k-val">{{ kpis.critical }}</span>
        <span class="k-lab">严重告警</span>
      </div>
      <div class="kpi">
        <span class="k-val">{{ kpis.prediction }}</span>
        <span class="k-lab">故障预测</span>
      </div>
      <div class="kpi" :class="{ bad: !connected }">
        <span class="k-val">{{ connected ? '正常' : '断连' }}</span>
        <span class="k-lab">平台状态</span>
      </div>
    </section>

    <section v-if="criticalHazard" class="hazard">
      <div class="h-title">
        <span class="badge">{{ criticalHazard.severity === 'critical' ? '严重' : '预警' }}</span>
        <strong>{{ criticalHazard.label_zh }}</strong>
        <span class="h-en">{{ criticalHazard.label_en }}</span>
      </div>
      <div class="h-chain">
        <span v-for="(c, i) in criticalHazard.chain" :key="i" class="link">
          {{ c }}
          <span v-if="i < criticalHazard.chain.length - 1" class="arrow">+</span>
        </span>
        <span class="arrow">⇒</span>
        <span class="conclusion">{{ criticalHazard.label_zh }}</span>
      </div>
      <div class="h-foot">
        跨 {{ criticalHazard.subsystems.length }} 个子系统 ·
        {{ criticalHazard.protocols.map((p: string) => p.toUpperCase()).join(' + ') }} 协议 ·
        由语义层统一关联 · 建议：{{ criticalHazard.recommended_action }}
      </div>
    </section>

    <section class="tiles">
      <article
        v-for="t in tiles"
        :key="t.key"
        class="tile"
        :class="{ off: !t.online, alarm: t.alarming }"
      >
        <div class="t-head">
          <span class="t-name">{{ t.label }}</span>
          <span class="t-proto">{{ t.proto }}</span>
        </div>
        <div class="t-body">
          <div v-for="r in t.readings" :key="r.prop" class="reading">
            <span class="r-val">{{ r.text }}</span>
            <span class="r-unit">{{ r.unit }}</span>
          </div>
        </div>
        <div class="t-foot">
          <span class="dot" :class="{ on: t.online }"></span>
          {{ t.online ? '在线' : '离线' }}
        </div>
      </article>
    </section>

    <section class="lower">
      <div class="graph-wrap">
        <h2>知识图谱 · 语义互操作</h2>
        <KnowledgeGraph />
      </div>
      <div class="side">
        <div class="agv-box">
          <h2>AGV 避障决策</h2>
          <div v-if="agv.length" class="agv-list">
            <div v-for="a in agv" :key="a.device_id" class="agv-row" :class="a.level">
              <span class="a-dev">{{ a.device_id }}</span>
              <span class="a-dist">{{ a.distance_cm }} cm</span>
              <span class="a-rate">{{ a.closing_rate_cm_s }} cm/s</span>
              <span class="a-lvl">{{ a.level.toUpperCase() }}</span>
            </div>
          </div>
          <div v-else class="empty">暂无 AGV 数据</div>
        </div>
        <div class="ticker">
          <h2>实时告警</h2>
          <div class="t-list">
            <div v-for="a in ticker" :key="a.id" class="t-row" :class="a.level">
              <span class="t-time">{{ timeOf(a.triggered_at) }}</span>
              <span class="t-lvl">{{ a.level === 'critical' ? '严重' : '预警' }}</span>
              <span class="t-msg">{{ a.message }}</span>
            </div>
            <div v-if="!ticker.length" class="empty">暂无告警</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.wall {
  position: fixed;
  inset: 0;
  background: radial-gradient(ellipse at top, #0f1e33 0%, #060b16 60%, #04070e 100%);
  color: #e2e8f0;
  display: grid;
  grid-template-rows: auto auto auto 1fr 1.15fr;
  gap: 14px;
  padding: 18px 24px 22px;
  overflow: hidden;
  font-family: 'Inter', system-ui, sans-serif;
}
.wall-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(56, 189, 248, 0.25);
  padding-bottom: 12px;
}
.left { display: flex; align-items: center; gap: 14px; }
.mark {
  width: 6px; height: 30px; border-radius: 3px;
  background: linear-gradient(#38bdf8, #6366f1);
}
.code { font-family: monospace; color: #38bdf8; font-size: 1rem; letter-spacing: 0.1em; }
h1 { font-size: 1.7rem; margin: 0; letter-spacing: 0.06em; font-weight: 600; }
.right { display: flex; align-items: center; gap: 18px; }
.os { color: #34d399; font-size: 0.82rem; }
.clock { font-family: monospace; font-size: 1.35rem; color: #7dd3fc; }
.exit {
  background: rgba(51, 65, 85, 0.7); color: #cbd5e1; border: 1px solid #475569;
  padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.75rem;
}

.kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
.kpi {
  background: rgba(30, 41, 59, 0.55);
  border: 1px solid #1e3a5f;
  border-radius: 10px;
  padding: 12px 18px;
  display: flex; flex-direction: column; gap: 4px;
}
.kpi.bad { border-color: #ef4444; background: rgba(69, 10, 10, 0.5); }
.k-val { font-size: 1.9rem; font-weight: 700; color: #7dd3fc; font-family: monospace; }
.kpi.bad .k-val { color: #fca5a5; }
.k-lab { font-size: 0.78rem; color: #94a3b8; }

.hazard {
  background: linear-gradient(90deg, rgba(127, 29, 29, 0.7), rgba(30, 41, 59, 0.5));
  border: 1px solid #ef4444;
  border-radius: 10px;
  padding: 12px 18px;
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 rgba(239, 68, 68, 0); }
  50% { box-shadow: 0 0 22px rgba(239, 68, 68, 0.45); }
}
.h-title { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.badge {
  background: #ef4444; color: #fff; padding: 2px 10px;
  border-radius: 4px; font-size: 0.72rem; font-weight: 700;
}
.h-title strong { font-size: 1.15rem; }
.h-en { color: #fca5a5; font-size: 0.82rem; }
.h-chain {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  font-family: monospace; font-size: 0.85rem; color: #fde68a;
}
.arrow { color: #f87171; font-weight: 700; margin: 0 4px; }
.conclusion { color: #fca5a5; font-weight: 700; }
.h-foot { margin-top: 8px; font-size: 0.78rem; color: #cbd5e1; }

.tiles { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
.tile {
  background: rgba(30, 41, 59, 0.5);
  border: 1px solid #1e3a5f;
  border-radius: 10px;
  padding: 14px 16px;
  display: flex; flex-direction: column; justify-content: space-between;
}
.tile.off { opacity: 0.45; }
.tile.alarm { border-color: #ef4444; background: rgba(69, 10, 10, 0.45); }
.t-head { display: flex; justify-content: space-between; align-items: center; }
.t-name { font-size: 0.92rem; color: #e2e8f0; }
.t-proto {
  font-family: monospace; font-size: 0.66rem; color: #fbbf24;
  border: 1px solid #78350f; border-radius: 3px; padding: 1px 6px;
}
.t-body { display: flex; gap: 16px; align-items: baseline; margin: 12px 0; }
.reading { display: flex; align-items: baseline; gap: 3px; }
.r-val { font-size: 2rem; font-weight: 700; font-family: monospace; color: #7dd3fc; }
.tile.alarm .r-val { color: #fca5a5; }
.r-unit { font-size: 0.78rem; color: #94a3b8; }
.t-foot { font-size: 0.74rem; color: #94a3b8; }
.dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #475569; display: inline-block; margin-right: 5px;
}
.dot.on { background: #34d399; box-shadow: 0 0 6px #34d399; }

.lower { display: grid; grid-template-columns: 1.6fr 1fr; gap: 14px; min-height: 0; }
.graph-wrap, .agv-box, .ticker {
  background: rgba(30, 41, 59, 0.5);
  border: 1px solid #1e3a5f;
  border-radius: 10px;
  padding: 12px 16px;
  min-height: 0;
  display: flex; flex-direction: column;
}
h2 { font-size: 0.88rem; color: #38bdf8; margin: 0 0 10px; font-weight: 600; }
.side { display: grid; grid-template-rows: auto 1fr; gap: 14px; min-height: 0; }
.agv-list { display: flex; flex-direction: column; gap: 6px; }
.agv-row {
  display: grid; grid-template-columns: 1.4fr 0.8fr 0.9fr 0.7fr;
  font-family: monospace; font-size: 0.76rem; padding: 5px 8px;
  border-radius: 5px; background: rgba(15, 23, 42, 0.6);
}
.agv-row.slow { border-left: 3px solid #fbbf24; }
.agv-row.stop { border-left: 3px solid #ef4444; background: rgba(69, 10, 10, 0.5); }
.a-lvl { text-align: right; color: #94a3b8; }
.agv-row.stop .a-lvl { color: #fca5a5; }

.t-list { overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.t-row {
  display: grid; grid-template-columns: auto auto 1fr;
  gap: 10px; font-size: 0.74rem; padding: 4px 8px; border-radius: 4px;
  background: rgba(15, 23, 42, 0.55);
}
.t-row.critical { border-left: 3px solid #ef4444; }
.t-row.warning { border-left: 3px solid #fbbf24; }
.t-time { font-family: monospace; color: #64748b; }
.t-lvl { color: #94a3b8; }
.t-row.critical .t-lvl { color: #fca5a5; }
.t-msg { color: #cbd5e1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { color: #64748b; font-size: 0.78rem; padding: 12px; text-align: center; }
</style>
