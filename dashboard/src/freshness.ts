import { ref, computed, onUnmounted, type Ref } from 'vue'

const now = ref(Date.now())
let subscribers = 0
let timer: ReturnType<typeof setInterval> | undefined

function start() {
  if (timer) return
  timer = setInterval(() => (now.value = Date.now()), 1000)
}

function stop() {
  if (timer && subscribers <= 0) {
    clearInterval(timer)
    timer = undefined
  }
}

export function useClock(): Ref<number> {
  subscribers += 1
  start()
  onUnmounted(() => {
    subscribers -= 1
    stop()
  })
  return now
}

export function ageMs(iso: string | null | undefined, at: number): number | null {
  if (!iso) return null
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return null
  return Math.max(0, at - t)
}

export function ageLabel(ms: number | null): string {
  if (ms === null) return '无数据'
  if (ms < 2000) return '刚刚更新'
  if (ms < 60_000) return `更新于 ${Math.floor(ms / 1000)} 秒前`
  if (ms < 3_600_000) return `更新于 ${Math.floor(ms / 60_000)} 分钟前`
  if (ms < 86_400_000) return `更新于 ${Math.floor(ms / 3_600_000)} 小时前`
  return `更新于 ${Math.floor(ms / 86_400_000)} 天前`
}

export function shortAge(ms: number | null): string {
  if (ms === null) return '--'
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s`
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h`
  return `${Math.floor(ms / 86_400_000)}d`
}

export function useFreshness(source: Ref<string | null | undefined>, staleMs = 120_000) {
  const clock = useClock()
  const age = computed(() => ageMs(source.value, clock.value))
  return {
    age,
    label: computed(() => ageLabel(age.value)),
    short: computed(() => shortAge(age.value)),
    stale: computed(() => age.value === null || age.value > staleMs),
  }
}

export function uptimeLabel(sinceIso: string | null | undefined, at: number): string {
  const ms = ageMs(sinceIso, at)
  if (ms === null) return '--'
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  if (h > 0) return `${h}小时${m}分`
  return `${m}分`
}
