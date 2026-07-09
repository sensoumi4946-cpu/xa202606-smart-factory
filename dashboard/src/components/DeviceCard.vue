<script setup lang="ts">
// Unified panel card extracted from DashboardView (Phase 3B). Wraps any
// panel in the shared rounded translucent card, renders a protocol badge in
// the top-right corner and emits a click carrying the device id. Set clickable
// to false for wide info panels (alerts, semantic) that have no drawer.
import { computed } from 'vue'
import { protoLabel } from '../deviceMeta'

const props = withDefaults(
  defineProps<{
    deviceId?: string
    protocol?: string
    clickable?: boolean
  }>(),
  { clickable: true },
)
const emit = defineEmits<{ open: [string] }>()

const tappable = computed(() => props.clickable && !!props.deviceId)

function onClick() {
  if (tappable.value && props.deviceId) emit('open', props.deviceId)
}</script>

<template>
  <div class="card" :class="{ tappable: tappable }" @click="onClick">
    <span v-if="protocol" class="badge">{{ protoLabel(protocol) }}</span>
    <slot />
  </div>
</template>

<style scoped>
.card {
  position: relative;
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 4px;
  transition: border-color 0.15s;
}
.card.tappable {
  cursor: pointer;
}
.card.tappable:hover {
  border-color: #38bdf8;
}
.badge {
  position: absolute;
  top: 8px;
  right: 10px;
  z-index: 2;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 0.66rem;
  color: #fbbf24;
  text-transform: uppercase;
}
</style>
