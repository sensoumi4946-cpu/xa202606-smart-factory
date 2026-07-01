const BASE_URL = '/'

export interface Device {
  device_id: string
}

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
}

export async function fetchDevices(): Promise<string[]> {
  const resp = await fetch(`${BASE_URL}api/v1/devices`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function fetchDeviceData(deviceId: string, limit = 100): Promise<SensorRecord[]> {
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
