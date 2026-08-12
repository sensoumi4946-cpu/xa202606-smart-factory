<script setup lang="ts">
// Live SHACL validation gate badge: ✓ PASSED / ✗ REJECTED, polled from
// GET /api/v1/semantic/gate-status. Three states:
//   passed   — last observation conformed to observation_shapes.ttl
//   rejected — last observation was refused by the gate (reason shown)
//   pending  — endpoint not implemented yet (returns 404) or unreachable
// The "pending" state keeps the badge honest while the gate integration
// branch is unmerged; the expected contract is documented in api.ts.
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchGateStatus, type GateStatus } from '../api'

const gate = ref<GateStatus | null>(null)
const pending = ref(true)
let timer: ReturnType<typeof setInterval> | undefined

async function refresh() {
  try {
    const data = await fetchGateStatus()
    gate.value = data
    pending.value = data === null
  } catch {
    gate.value = null
    pending.value = true
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
  <span
    class="gate-badge mono"
    :class="pending ? 'pending' : gate?.status"
    :title="
      pending
        ? 'SHACL 网关状态端点待接入 (/api/v1/semantic/gate-status)'
        : gate?.status === 'rejected'
          ? `${gate?.last_device ?? ''}: ${gate?.reason ?? ''}`
          : `已通过 ${gate?.passed_count ?? '—'} · 已拒绝 ${gate?.rejected_count ?? '—'}`
    "
  >
    <template v-if="pending">SHACL · 待接入</template>
    <template v-else-if="gate?.status === 'passed'">✓ SHACL PASSED</template>
    <template v-else>✗ SHACL REJECTED</template>
  </span>
</template>

<style scoped>
.gate-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  border: 1px solid var(--line-strong);
  cursor: help;
}
.gate-badge.passed {
  color: var(--ok);
  border-color: var(--ok);
  background: var(--ok-bg);
}
.gate-badge.rejected {
  color: var(--danger);
  border-color: var(--danger);
  background: var(--danger-bg);
  animation: flash 1s ease-in-out infinite;
}
.gate-badge.pending {
  color: var(--text-faint);
}
@keyframes flash {
  50% {
    opacity: 0.65;
  }
}
</style>
