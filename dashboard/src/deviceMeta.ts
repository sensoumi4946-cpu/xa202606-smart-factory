import { reactive } from 'vue'
import { fetchDeviceRegistry } from './api'

export interface DeviceMeta {
  protocol: string
  subsystem: string
  connectVia: string
  lastSeen: string
}

const _CONNECT_VIA_FALLBACK: Record<string, string> = {
  mqtt: 'MQTT topic (see connectivity/adapters/mqtt_adapter.py)',
  modbus: 'Modbus holding registers (see connectivity/adapters/modbus_adapter.py)',
  opcua: 'OPC UA subscription (see connectivity/adapters/opcua_adapter.py)',
  rest: 'POST /adapter/rest/ingest',
}

export const DEVICE_META = reactive<Record<string, DeviceMeta>>({})

let _loadingPromise: Promise<void> | null = null

async function _load(): Promise<void> {
  try {
    const registry = await fetchDeviceRegistry()
    for (const entry of registry) {
      DEVICE_META[entry.device_id] = {
        protocol: entry.protocol,
        subsystem: entry.subsystem,
        connectVia: _CONNECT_VIA_FALLBACK[entry.protocol] ?? entry.protocol,
        lastSeen: entry.last_seen,
      }
    }
  } catch {
    
  }
}

export function ensureDeviceMetaLoaded(): Promise<void> {
  if (!_loadingPromise) _loadingPromise = _load()
  return _loadingPromise
}

export function refreshDeviceMeta(): Promise<void> {
  _loadingPromise = _load()
  return _loadingPromise
}

export function protoLabel(proto: string | undefined): string {
  if (!proto) return '--'
  if (proto === 'opcua') return 'OPC UA'
  return proto.toUpperCase()
}

export const SUBSYSTEM_LABEL: Record<string, string> = {
  temp_humidity: '温湿度',
  lighting: '照明感应',
  gas: '危险气体',
  agv: 'AGV 避障',
  counting: '货物计数',
}

export function subsystemLabel(key: string | undefined): string {
  if (!key) return '--'
  return SUBSYSTEM_LABEL[key] ?? key
}