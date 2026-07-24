<script setup lang="ts">
// The dashboard's opening statement: answers "is the factory safe?"
// in one glance. Overall state is computed from active alerts:
//   critical alert in last 60s -> CRITICAL (red)
//   warning  alert in last 60s -> WARNING  (amber)
//   otherwise                  -> NORMAL   (green)
// Right side: four live KPIs (devices, msgs/10min, alerts, semantic gate).
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  fetchAlerts,
  fetchDevices,
  fetchHistory,
  probeFuseki,
  type AlertItem,
} from '../api'

const RECENT_MS = 60_000

const alerts = ref<AlertItem[]>([])
const deviceCount = ref<number | null>(null)
const recentMsgs = ref<number | null>(null)
const fusekiOk = ref<boolean | null>(null)

let fastTimer: ReturnType<typeof setInterval> | undefined
let slowTimer: ReturnType<typeof setInterval> | undefined

const recentAlerts = computed(() =>
  alerts.value.filter(
    (a) => Date.now() - new Date(a.triggered_at).getTime() < RECENT_MS,
  ),
)

const state = computed<'normal' | 'warning' | 'critical'>(() => {
  if (recentAlerts.value.some((a) => a.level === 'critical')) return 'critical'
  if (recentAlerts.value.some((a) => a.level === 'warning')) return 'warning'
  return 'normal'
})

const STATE_TEXT = {
  normal: { zh: '系统正常', en: 'ALL SYSTEMS NORMAL' },
  warning: { zh: '出现异常', en: 'ANOMALY DETECTED' },
  critical: { zh: '严重告警', en: 'CRITICAL ALERT' },
}

async function refreshFast() {
  try {
    const data = await fetchAlerts({ limit: 30 })
    alerts.value = data.items
  } catch {
    /* keep last known */
  }
}

async function refreshSlow() {
  try {
    deviceCount.value = (await fetchDevices()).length
  } catch {
    deviceCount.value = null
  }
  try {
    const since = new Date(Date.now() - 10 * 60 * 1000).toISOString()
    recentMsgs.value = (await fetchHistory({ since, limit: 1 })).total
  } catch {
    recentMsgs.value = null
  }
  fusekiOk.value = await probeFuseki().catch(() => false)
}

onMounted(() => {
  refreshFast()
  refreshSlow()
  fastTimer = setInterval(refreshFast, 3000)
  slowTimer = setInterval(refreshSlow, 10000)
})
onUnmounted(() => {
  if (fastTimer) clearInterval(fastTimer)
  if (slowTimer) clearInterval(slowTimer)
})
</script>

<template>
  <section class="pulse" :class="state" aria-live="polite">
    <div class="edge" :class="state" aria-hidden="true"></div>

    <div class="state">
      <span class="beacon" :class="state" aria-hidden="true"></span>
      <div class="words">
        <span class="zh">{{ STATE_TEXT[state].zh }}</span>
        <span class="en mono">{{ STATE_TEXT[state].en }}</span>
      </div>
    </div>

    <div class="kpis">
      <div class="kpi">
        <span class="k mono">{{ deviceCount ?? '—' }}</span>
        <span class="l">已注册设备</span>
      </div>
      <div class="kpi">
        <span class="k mono">{{ recentMsgs ?? '—' }}</span>
        <span class="l">近10分钟消息</span>
      </div>
      <div class="kpi">
        <span class="k mono" :class="{ hot: recentAlerts.length > 0 }">{{
          recentAlerts.length
        }}</span>
        <span class="l">活动告警</span>
      </div>
      <div class="kpi">
        <span class="k mono gate" :class="fusekiOk ? 'ok' : 'down'">
          {{ fusekiOk === null ? '—' : fusekiOk ? 'PASS' : 'DOWN' }}
        </span>
        <span class="l">语义校验网关</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.pulse {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gap);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px 18px 14px 26px;
  overflow: hidden;
  flex-wrap: wrap;
}

/* Signature: hazard-stripe edge, colored by state */
.edge {
  position: absolute;
  inset: 0 auto 0 0;
  width: 10px;
}
.edge.normal {
  background: var(--ok);
}
.edge.warning {
  background: repeating-linear-gradient(
    -45deg,
    var(--warn) 0 8px,
    #161b22 8px 16px
  );
}
.edge.critical {
  background: repeating-linear-gradient(
    -45deg,
    var(--danger) 0 8px,
    #161b22 8px 16px
  );
  animation: crawl 1.2s linear infinite;
}
@keyframes crawl {
  to {
    background-position: 0 22.6px;
  }
}

.state {
  display: flex;
  align-items: center;
  gap: 14px;
}
.beacon {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  flex: none;
}
.beacon.normal {
  background: var(--ok);
  box-shadow: 0 0 10px rgba(76, 195, 138, 0.7);
}
.beacon.warning {
  background: var(--warn);
  box-shadow: 0 0 10px rgba(245, 165, 36, 0.7);
}
.beacon.critical {
  background: var(--danger);
  box-shadow: 0 0 12px rgba(240, 68, 68, 0.9);
  animation: throb 0.9s ease-in-out infinite;
}
@keyframes throb {
  50% {
    transform: scale(1.25);
  }
}
.words {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.zh {
  font-size: var(--fs-xl);
  font-weight: 700;
  line-height: 1.1;
}
.en {
  font-size: var(--fs-xs);
  color: var(--text-dim);
  letter-spacing: 0.14em;
}
.pulse.critical .zh {
  color: var(--danger);
}
.pulse.warning .zh {
  color: var(--warn);
}

.kpis {
  display: flex;
  gap: 28px;
  flex-wrap: wrap;
}
.kpi {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.k {
  font-size: var(--fs-lg);
  font-weight: 600;
}
.k.hot {
  color: var(--warn);
}
.k.gate.ok {
  color: var(--ok);
}
.k.gate.down {
  color: var(--danger);
}
.l {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}

@media (max-width: 700px) {
  .kpis {
    gap: 18px;
  }
  .kpi {
    align-items: flex-start;
  }
}
</style>
