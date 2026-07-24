<script setup lang="ts">
// Unified panel card. Wraps any panel in the shared surface card, renders
// a protocol badge in the top-right corner and emits a click carrying the
// device id. Set clickable to false for wide info panels (alerts, semantic)
// that have no drawer.
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
    <span v-if="protocol" class="badge mono">{{ protoLabel(protocol) }}</span>
    <slot />
  </div>
</template>

<style scoped>
.card {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 4px;
  transition: border-color 0.15s var(--ease), transform 0.15s var(--ease);
}
.card.tappable {
  cursor: pointer;
}
.card.tappable:hover {
  border-color: var(--warn);
  transform: translateY(-1px);
}
.badge {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 2;
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  padding: 1px 7px;
  font-size: var(--fs-xs);
  color: var(--text-dim);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
</style>
