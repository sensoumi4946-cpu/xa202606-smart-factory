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
    <p class="title">{{ title }}</p>
    <p v-if="detail" class="detail">{{ detail }}</p>
    <p v-if="hint" class="hint">{{ hint }}</p>
    <button class="retry" @click="emit('retry')">{{ retryLabel }}</button>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 48px 24px;
  text-align: center;
  border: 1px dashed var(--line-strong);
  background: var(--surface);
}
.title { margin: 0; font-size: 14px; color: var(--text-dim); }
.empty.error .title, .empty.offline .title { color: var(--danger); }
.detail { margin: 0; font-size: 12px; color: var(--text-faint); max-width: 460px; line-height: 1.7; }
.hint {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--text-faint);
  font-family: 'JetBrains Mono', monospace;
}
.retry {
  margin-top: 10px;
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  color: var(--text-dim);
  font-size: 12px;
  padding: 5px 18px;
  cursor: pointer;
}
.retry:hover { color: var(--text); }
</style>
