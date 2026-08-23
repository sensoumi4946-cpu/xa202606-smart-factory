<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchGateStatus, type GateStatus } from '../api'

const status = ref<GateStatus | null>(null)
let timer: ReturnType<typeof setInterval> | undefined

const passed = computed(() => status.value?.passed_count ?? 0)
const rejected = computed(() => status.value?.rejected_count ?? 0)

const state = computed(() => {
  if (!status.value || passed.value + rejected.value === 0) return 'pending'
  return 'active'
})

const label = computed(() => {
  if (state.value === 'pending') return '待接入'
  return `${passed.value} 通过 / ${rejected.value} 拦截`
})

const hint = computed(() => {
  if (state.value === 'pending') return '尚无入库记录'
  const last = status.value?.last_device ?? ''
  const reason = status.value?.reason
  return reason ? `最近一次：${last} — ${reason}` : `最近一次：${last} 通过`
})

async function refresh() {
  try {
    status.value = await fetchGateStatus()
  } catch {
    status.value = null
  }
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
  <span class="badge" :class="state" :title="hint">
    <span class="dot"></span>
    SHACL · {{ label }}
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-xs, 0.72rem);
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--line-strong, #334155);
  color: var(--text-dim, #94a3b8);
  cursor: default;
  white-space: nowrap;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #64748b;
}
.badge.active {
  border-color: #34d399;
  color: #34d399;
}
.badge.active .dot {
  background: #34d399;
}
</style>