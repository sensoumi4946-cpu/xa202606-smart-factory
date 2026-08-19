<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useFreshness } from '../freshness'

const props = withDefaults(
  defineProps<{
    title: string
    protocol?: string
    timestamp?: string | null
    state?: 'ok' | 'warn' | 'danger' | 'idle'
    dense?: boolean
  }>(),
  { protocol: '', timestamp: null, state: 'idle', dense: false },
)

const { label, stale } = useFreshness(toRef(props, 'timestamp'))

const protoLabel = computed(() => {
  if (!props.protocol) return ''
  return props.protocol === 'opcua' ? 'OPC UA' : props.protocol.toUpperCase()
})
</script>

<template>
  <section class="panel" :class="[state, { dense }]">
    <header class="head">
      <h2>{{ title }}</h2>
      <div class="meta">
        <span v-if="protoLabel" class="proto mono">{{ protoLabel }}</span>
        <span class="age" :class="{ stale }">{{ label }}</span>
      </div>
    </header>
    <div class="body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 2px solid var(--line-strong);
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.panel.ok { border-left-color: var(--ok); }
.panel.warn { border-left-color: var(--warn); }
.panel.danger { border-left-color: var(--danger); }

.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px 6px;
  border-bottom: 1px solid var(--line);
}
h2 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.02em;
}
.meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.proto {
  font-size: 10px;
  color: var(--text-faint);
  border: 1px solid var(--line-strong);
  padding: 0 5px;
  line-height: 15px;
}
.age {
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}
.age.stale { color: var(--warn); }

.body {
  padding: 10px 12px 12px;
  flex: 1;
  min-height: 0;
}
.panel.dense .body { padding: 6px 10px 8px; }
</style>
