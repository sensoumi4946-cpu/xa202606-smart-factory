<script setup lang="ts">
// Live alert feed. Cross-subsystem correlation alerts get their own
// stronger row treatment so single-sensor warnings and correlated events
// read as different severities at a glance.
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

function isCross(a: AlertItem): boolean {
  return a.subsystem === 'cross_subsystem'
}

async function refresh() {
  try {
    const data = await fetchAlerts({ limit: 20 })
    alerts.value = data.items
    error.value = ''
  } catch {
    error.value = '告警数据加载失败'
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
    <header class="head">
      <h3>告警面板</h3>
      <select v-model="filterLevel" class="filter" aria-label="按级别筛选">
        <option value="">全部</option>
        <option value="warning">Warning</option>
        <option value="critical">Critical</option>
      </select>
    </header>
    <div v-if="error" class="err">{{ error }}</div>
    <div v-else-if="!filtered.length" class="empty">
      暂无告警 — 系统运行正常
    </div>
    <TransitionGroup v-else name="row" tag="div" class="rows">
      <div
        v-for="a in filtered"
        :key="a.id"
        class="alert-row"
        :class="[a.level, { cross: isCross(a) }]"
      >
        <span class="level-badge mono" :class="a.level">
          {{ isCross(a) ? 'CROSS' : a.level }}
        </span>
        <span class="msg" :title="a.message">{{ a.message }}</span>
        <span class="time mono">{{
          new Date(a.triggered_at).toLocaleTimeString()
        }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.panel {
  padding: var(--pad);
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
h3 {
  color: var(--text);
  font-size: var(--fs-md);
  margin: 0;
}
.filter {
  background: var(--surface-2);
  color: var(--text);
  border: 1px solid var(--line-strong);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-family: var(--font-ui);
  font-size: var(--fs-sm);
}
.rows {
  max-height: 300px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.alert-row {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 7px 10px;
  font-size: var(--fs-sm);
  border-radius: var(--radius-sm);
  border-left: 3px solid transparent;
}
.alert-row.warning {
  background: var(--warn-bg);
  border-left-color: var(--warn);
}
.alert-row.critical {
  background: var(--danger-bg);
  border-left-color: var(--danger);
}
.alert-row.cross {
  border: 1px solid var(--danger);
  border-left-width: 3px;
}
.level-badge {
  padding: 1px 7px;
  border-radius: 3px;
  font-weight: 700;
  text-transform: uppercase;
  font-size: var(--fs-xs);
  flex: none;
}
.level-badge.warning {
  background: var(--warn);
  color: #14100a;
}
.level-badge.critical {
  background: var(--danger);
  color: #fff;
}
.msg {
  flex: 1;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.time {
  color: var(--text-dim);
  white-space: nowrap;
  font-size: var(--fs-xs);
}
.empty {
  color: var(--text-faint);
  padding: 16px 0;
  font-size: var(--fs-sm);
}
.err {
  color: var(--danger);
  font-size: var(--fs-sm);
  padding: 8px 0;
}
.row-enter-active {
  transition: all 0.25s var(--ease);
}
.row-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
