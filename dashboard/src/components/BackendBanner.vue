<script setup lang="ts">
import { computed } from 'vue'
import { usePoll } from '../usePoll'
import { rawRequest } from '../api'

interface Probe {
  ok: boolean
  detail: string
}

async function probeHealth(): Promise<Probe> {
  try {
    const res = await rawRequest('GET', '/health')
    return { ok: res.ok, detail: res.ok ? '' : `HTTP ${res.status}` }
  } catch (err) {
    return { ok: false, detail: String(err).slice(0, 80) }
  }
}

const { data, refresh } = usePoll<Probe>('health', probeHealth, 5000)

const checked = computed(() => data.value !== null)
const online = computed(() => data.value?.ok ?? true)
const lastError = computed(() => data.value?.detail ?? '')
</script>

<template>
  <div v-if="checked && !online" class="banner">
    <span class="mark">●</span>
    <span class="text">后端服务未连接</span>
    <span class="detail mono">
      请确认 backend 已启动（端口 8000）{{ lastError ? ' · ' + lastError : '' }}
    </span>
    <button class="retry" @click="refresh">重试</button>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 7px 16px;
  background: var(--danger-bg);
  border-bottom: 1px solid var(--danger);
  font-size: 12px;
}
.mark { color: var(--danger); font-size: 9px; }
.text { color: var(--danger); font-weight: 600; }
.detail { color: var(--text-dim); font-size: 11px; }
.retry {
  margin-left: auto;
  background: transparent;
  border: 1px solid var(--danger);
  color: var(--danger);
  font-size: 11px;
  padding: 2px 12px;
  cursor: pointer;
}
</style>