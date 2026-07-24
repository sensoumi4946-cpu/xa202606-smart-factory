<script setup lang="ts">
// Renders only when a cross-subsystem correlation alert is active
// (subsystem === 'cross_subsystem', e.g. fire risk from temperature + CO
// inside the 10s correlation window). This is the single most important
// moment of the demo, so the banner shows the causal chain explicitly:
//   [temp sensor] --\
//                    >-- correlated --> FIRE RISK
//   [gas sensor]  --/
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchAlerts, type AlertItem } from '../api'

const ACTIVE_MS = 60_000

const alerts = ref<AlertItem[]>([])
let timer: ReturnType<typeof setInterval> | undefined

const active = computed<AlertItem | null>(() => {
  const found = alerts.value.find(
    (a) =>
      a.subsystem === 'cross_subsystem' &&
      Date.now() - new Date(a.triggered_at).getTime() < ACTIVE_MS,
  )
  return found ?? null
})

const sourceDevices = computed(() =>
  active.value ? active.value.device_id.split('+') : [],
)

async function refresh() {
  try {
    const data = await fetchAlerts({ level: 'critical', limit: 10 })
    alerts.value = data.items
  } catch {
    /* keep last known */
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
  <Transition name="drop">
    <section v-if="active" class="banner" role="alert">
      <div class="chain" aria-hidden="true">
        <div class="sources">
          <span v-for="d in sourceDevices" :key="d" class="node mono">{{
            d
          }}</span>
        </div>
        <svg class="wires" viewBox="0 0 60 64" preserveAspectRatio="none">
          <path d="M0 14 C 30 14, 30 32, 60 32" />
          <path d="M0 50 C 30 50, 30 32, 60 32" />
        </svg>
        <span class="event mono">FIRE RISK</span>
      </div>

      <div class="body">
        <span class="title">跨子系统关联告警</span>
        <span class="msg">{{ active.message }}</span>
        <span class="meta mono">
          {{ active.rule_name }} ·
          {{ new Date(active.triggered_at).toLocaleTimeString() }}
        </span>
      </div>
    </section>
  </Transition>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: center;
  gap: 22px;
  background: var(--danger-bg);
  border: 1px solid var(--danger);
  border-radius: var(--radius);
  padding: 12px 18px;
  flex-wrap: wrap;
}

.chain {
  display: flex;
  align-items: center;
  gap: 0;
  flex: none;
}
.sources {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.node {
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  padding: 3px 8px;
  font-size: var(--fs-xs);
  color: var(--text);
}
.wires {
  width: 60px;
  height: 64px;
}
.wires path {
  fill: none;
  stroke: var(--danger);
  stroke-width: 1.6;
  stroke-dasharray: 5 4;
  animation: flow 0.8s linear infinite;
}
@keyframes flow {
  to {
    stroke-dashoffset: -9;
  }
}
.event {
  background: var(--danger);
  color: #fff;
  border-radius: var(--radius-sm);
  padding: 5px 10px;
  font-weight: 700;
  font-size: var(--fs-sm);
  letter-spacing: 0.08em;
}

.body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 220px;
}
.title {
  font-weight: 700;
  color: var(--danger);
  font-size: var(--fs-md);
}
.msg {
  font-size: var(--fs-sm);
}
.meta {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}

.drop-enter-active {
  transition: all 0.3s var(--ease);
}
.drop-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
