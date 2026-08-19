<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchGateStatus, type GateStatus } from '../api'

const status = ref<GateStatus | null>(null)
let timer: ReturnType<typeof setInterval> | undefined

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
  <span
    class="badge"
    :class="status?.status ?? 'pending'"
    :title="
      status
        ? `${status.passed_count ?? 0} 通过 / ${status.rejected_count ?? 0} 拒绝` +
          (status.status === 'rejected' && status.reason ? ' — ' + status.reason : '')
        : '尚无入库记录'
    "
  >
    <span class="dot"></span>
    SHACL ·
    {{
      status?.status === 'passed'
        ? '通过'
        : status?.status === 'rejected'
          ? '拒绝'
          : '待接入'
    }}
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
.badge.passed {
  border-color: #34d399;
  color: #34d399;
}
.badge.passed .dot {
  background: #34d399;
}
.badge.rejected {
  border-color: var(--danger, #ef4444);
  color: var(--danger, #ef4444);
}
.badge.rejected .dot {
  background: var(--danger, #ef4444);
}
</style>
