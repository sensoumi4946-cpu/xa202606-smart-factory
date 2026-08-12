import { fetchDeviceRegistry } from './api'

export interface DeviceMeta {
  protocol: string
  subsystem: string
  connectVia: string
}

const _CONNECT_VIA_FALLBACK: Record<string, string> = {
  mqtt: 'MQTT topic (see connectivity/adapters/mqtt_adapter.py)',
  modbus: 'Modbus holding registers (see connectivity/adapters/modbus_adapter.py)',
  opcua: 'OPC UA subscription (see connectivity/adapters/opcua_adapter.py)',
  rest: 'POST /adapter/rest/ingest',
}

export const DEVICE_META: Record<string, DeviceMeta> = {}

let _loaded = false
let _loadingPromise: Promise<void> | null = null

async function _load(): Promise<void> {
  try {
    const registry = await fetchDeviceRegistry()
    for (const entry of registry) {
      DEVICE_META[entry.device_id] = {
        protocol: entry.protocol,
        subsystem: entry.subsystem,
        connectVia: _CONNECT_VIA_FALLBACK[entry.protocol] ?? entry.protocol,
      }
    }
    _loaded = true
  } catch {
    // Leave DEVICE_META empty on failure; callers already handle a
    // missing entry gracefully (optional-chained lookups).
  }
}

// Call this once near app startup (e.g. in App.vue's onMounted) so
// DEVICE_META is populated before components read from it. Safe to call
// multiple times — only fetches once.
export function ensureDeviceMetaLoaded(): Promise<void> {
  if (_loaded) return Promise.resolve()
  if (!_loadingPromise) _loadingPromise = _load()
  return _loadingPromise
}

export function protoLabel(proto: string): string {
  if (proto === 'opcua') return 'OPC UA'
  return proto.toUpperCase()
}
