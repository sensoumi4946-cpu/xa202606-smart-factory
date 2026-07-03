const BASE_URL = '/'

export interface SensorRecord {
  id: string
  device_id: string
  subsystem: string
  protocol: string
  timestamp: string
  measurements: Array<{
    type: string
    value: number
    unit: string
  }>
  raw_payload?: Record<string, unknown>
}

export interface LatestDevice {
  device_id: string
  subsystem: string
  measurements: Array<{
    type: string
    value: number
    unit: string
    timestamp: string
  }>
}

export interface AlertItem {
  id: string
  rule_name: string
  level: 'warning' | 'critical'
  device_id: string
  subsystem: string
  measurement_type: string
  value: number
  threshold: number
  message: string
  source_record_id: string
  triggered_at: string
}

export interface Paginated<T> {
  items: T[]
  total: number
}

export async function fetchDevices(): Promise<string[]> {
  const resp = await fetch(`${BASE_URL}api/v1/devices`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function fetchDeviceData(
  deviceId: string,
  limit = 100,
): Promise<SensorRecord[]> {
  const params = new URLSearchParams({ device_id: deviceId, limit: String(limit) })
  const resp = await fetch(`${BASE_URL}api/v1/data?${params}`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function fetchAllData(limit = 100): Promise<SensorRecord[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  const resp = await fetch(`${BASE_URL}api/v1/data?${params}`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function fetchLatest(
  deviceId?: string,
): Promise<LatestDevice[]> {
  const params = deviceId
    ? `?device_id=${encodeURIComponent(deviceId)}`
    : ''
  const resp = await fetch(`${BASE_URL}api/v1/latest${params}`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function fetchHistory(params: {
  device_id?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
}): Promise<Paginated<SensorRecord>> {
  const sp = new URLSearchParams()
  if (params.device_id) sp.set('device_id', params.device_id)
  if (params.since) sp.set('since', params.since)
  if (params.until) sp.set('until', params.until)
  if (params.limit !== undefined) sp.set('limit', String(params.limit))
  if (params.offset !== undefined) sp.set('offset', String(params.offset))
  const qs = sp.toString()
  const resp = await fetch(`${BASE_URL}api/v1/history${qs ? '?' + qs : ''}`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function fetchAlerts(params: {
  device_id?: string
  level?: string
  limit?: number
  offset?: number
}): Promise<Paginated<AlertItem>> {
  const sp = new URLSearchParams()
  if (params.device_id) sp.set('device_id', params.device_id)
  if (params.level) sp.set('level', params.level)
  if (params.limit !== undefined) sp.set('limit', String(params.limit))
  if (params.offset !== undefined) sp.set('offset', String(params.offset))
  const qs = sp.toString()
  const resp = await fetch(`${BASE_URL}api/v1/alerts${qs ? '?' + qs : ''}`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}
