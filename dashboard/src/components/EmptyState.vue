<script setup lang="ts">
withDefaults(
  defineProps<{
    kind?: 'offline' | 'empty' | 'error'
    title: string
    detail?: string
    hint?: string
    retryLabel?: string
  }>(),
  { kind: 'empty', detail: '', hint: '', retryLabel: '重试' },
)

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="empty" :class="kind">
    <div class="inner">
      <span class="dot"></span>
      <p class="title">{{ title }}</p>
      <p v-if="detail" class="detail">{{ detail }}</p>
      <code v-if="hint" class="hint">{{ hint }}</code>
      <button class="retry" @click="emit('retry')">{{ retryLabel }}</button>
    </div>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 140px);
  width: 100%;
  padding: 24px;
  box-sizing: border-box;
}
.inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  max-width: 520px;
  width: 100%;
  padding: 40px 32px;
  text-align: center;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 10px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-faint);
  box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.04);
}
.empty.offline .dot,
.empty.error .dot {
  background: var(--danger);
  box-shadow: 0 0 0 4px var(--danger-bg);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  50% { opacity: 0.35; }
}
.title {
  margin: 2px 0 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.02em;
}
.empty.offline .title,
.empty.error .title {
  color: var(--danger);
}
.detail {
  margin: 0;
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.8;
}
.hint {
  display: block;
  width: 100%;
  box-sizing: border-box;
  margin-top: 4px;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 5px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
  text-align: left;
  overflow-x: auto;
}
.retry {
  margin-top: 6px;
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  color: var(--text);
  font-size: 12px;
  font-family: var(--font-ui);
  padding: 7px 26px;
  border-radius: 5px;
  cursor: pointer;
}
.retry:hover {
  border-color: var(--warn);
  color: var(--warn);
}
.retry:focus-visible {
  outline: 2px solid var(--warn);
  outline-offset: 2px;
}
</style>