import { ref, onMounted, onUnmounted, type Ref } from 'vue'

type Fetcher<T> = () => Promise<T>

interface Channel<T> {
  data: Ref<T | null>
  error: Ref<unknown>
  loading: Ref<boolean>
  refs: number
  timer: ReturnType<typeof setInterval> | undefined
  intervalMs: number
  fetcher: Fetcher<T>
  inflight: Promise<void> | null
}

const _channels = new Map<string, Channel<unknown>>()

let _visible = true
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    _visible = document.visibilityState === 'visible'
    if (_visible) {
      for (const ch of _channels.values()) void _run(ch)
    }
  })
}

async function _run(ch: Channel<unknown>): Promise<void> {
  if (ch.inflight) return ch.inflight
  ch.loading.value = ch.data.value === null
  ch.inflight = (async () => {
    try {
      ch.data.value = await ch.fetcher()
      ch.error.value = null
    } catch (e) {
      ch.error.value = e
    } finally {
      ch.loading.value = false
      ch.inflight = null
    }
  })()
  return ch.inflight
}

function _start(ch: Channel<unknown>): void {
  if (ch.timer) return
  void _run(ch)
  ch.timer = setInterval(() => {
    if (_visible) void _run(ch)
  }, ch.intervalMs)
}

function _stop(ch: Channel<unknown>): void {
  if (ch.timer) clearInterval(ch.timer)
  ch.timer = undefined
}

export function usePoll<T>(
  key: string,
  fetcher: Fetcher<T>,
  intervalMs = 2000,
) {
  let ch = _channels.get(key) as Channel<T> | undefined

  if (!ch) {
    ch = {
      data: ref(null) as Ref<T | null>,
      error: ref(null),
      loading: ref(true),
      refs: 0,
      timer: undefined,
      intervalMs,
      fetcher,
      inflight: null,
    }
    _channels.set(key, ch as Channel<unknown>)
  } else if (intervalMs < ch.intervalMs) {
    ch.intervalMs = intervalMs
    _stop(ch as Channel<unknown>)
    _start(ch as Channel<unknown>)
  }

  const channel = ch

  onMounted(() => {
    channel.refs += 1
    _start(channel as Channel<unknown>)
  })

  onUnmounted(() => {
    channel.refs -= 1
    if (channel.refs <= 0) _stop(channel as Channel<unknown>)
  })

  return {
    data: channel.data,
    error: channel.error,
    loading: channel.loading,
    refresh: () => _run(channel as Channel<unknown>),
  }
}

export function refreshAll(): void {
  for (const ch of _channels.values()) void _run(ch)
}

export function resetPolls(): void {
  for (const ch of _channels.values()) _stop(ch)
  _channels.clear()
}

export function pollStats(): Array<{ key: string; refs: number; ms: number }> {
  return [..._channels.entries()].map(([key, ch]) => ({
    key,
    refs: ch.refs,
    ms: ch.intervalMs,
  }))
}