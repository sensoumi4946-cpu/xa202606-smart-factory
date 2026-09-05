import { ref } from 'vue'
import { fetchDeviceRegistry, fetchLatestDeduped, type LatestDevice } from './api'

export interface ResolvedDevice {
  deviceId: string
  protocol: string
  subsystem: string
}

const _bySubsystem = ref<Record<string, ResolvedDevice>>({})
const _latest = ref<LatestDevice[]>([])
const _error = ref<Error | null>(null)
let _timer: ReturnType<typeof setInterval> | undefined
let _refs = 0

export function devicesBySubsystem() {
  return _bySubsystem
}

export function latestSnapshot() {
  return _latest
}

export function deviceForSubsystem(subsystem: string): ResolvedDevice | undefined {
  return _bySubsystem.value[subsystem]
}

export function measurementFor(
  subsystem: string,
  type: string,
): { value: number; unit: string; timestamp: string } | null {
  const dev = _bySubsystem.value[subsystem]
  if (!dev) return null
  const entry = _latest.value.find((d) => d.device_id === dev.deviceId)
  if (!entry) return null
  const m = entry.measurements.find((x) => x.type === type)
  return m ? { value: m.value, unit: m.unit, timestamp: m.timestamp } : null
}

async function refresh(): Promise<void> {
  try {
    const [registry, latest] = await Promise.all([
      fetchDeviceRegistry(),
      fetchLatestDeduped(),
    ])
    const map: Record<string, ResolvedDevice> = {}
    // Newest last_seen wins when several devices claim one subsystem.
    for (const e of [...registry].sort(
      (a, b) => new Date(a.last_seen).getTime() - new Date(b.last_seen).getTime(),
    )) {
      map[e.subsystem] = {
        deviceId: e.device_id,
        protocol: e.protocol,
        subsystem: e.subsystem,
      }
    }
    _bySubsystem.value = map
    _latest.value = latest
    _error.value = null
  } catch (error) {
    _error.value = error instanceof Error ? error : new Error(String(error))
  }
}

export function useSubsystemDevices(intervalMs = 2000) {
  _refs += 1
  if (!_timer) {
    refresh()
    _timer = setInterval(refresh, intervalMs)
  }
  return {
    release() {
      _refs -= 1
      if (_refs <= 0 && _timer) {
        clearInterval(_timer)
        _timer = undefined
        _refs = 0
      }
    },
    refresh,
    error: _error,
  }
}
