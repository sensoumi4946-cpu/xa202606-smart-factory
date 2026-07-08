<script setup lang="ts">
// Minimal read-only JSON formatter. Renders the value via
// JSON.stringify(value, null, 2) inside a scrollable <pre>. No folding
// tree by design (see Phase 3A spec).
defineProps<{ value: unknown }>()

function pretty(v: unknown): string {
  if (v === null || v === undefined) return String(v)
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}
</script>

<template>
  <pre class="json">{{ pretty(value) }}</pre>
</template>

<style scoped>
.json {
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 10px 12px;
  margin: 0;
  font-family: 'Cascadia Code', Consolas, monospace;
  font-size: 0.78rem;
  color: #a5f3fc;
  white-space: pre-wrap;
  word-break: break-word;
  overflow: auto;
  max-height: 420px;
}
</style>
