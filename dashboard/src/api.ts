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

export interface SemanticSensor {
  sensor: string
  subsystem: string
  observes: string[]
  protocol: string
}

export interface SemanticView {
  view: string
  description: string
  results: SemanticSensor[]
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

// Deduped variant: when multiple components call fetchLatest() without
// device_id within the same tick, only one backend request is sent.
let _pendingLatest: Promise<LatestDevice[]> | null = null
export async function fetchLatestDeduped(
  deviceId?: string,
): Promise<LatestDevice[]> {
  if (deviceId) return fetchLatest(deviceId)
  if (!_pendingLatest) {
    _pendingLatest = fetchLatest().finally(() => {
      _pendingLatest = null
    })
  }
  return _pendingLatest
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

export async function fetchSemanticView(
  view = 'sensor-observations',
): Promise<SemanticView> {
  const params = new URLSearchParams({ view })
  const resp = await fetch(`${BASE_URL}api/v1/semantic?${params}`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export interface RawResult {
  status: number
  ok: boolean
  ms: number
  body: unknown
}

// Generic request used by the API Console. Returns status, elapsed time
// and parsed body without throwing on non-2xx so the UI can render errors.
export async function rawRequest(
  method: string,
  path: string,
  body?: unknown,
): Promise<RawResult> {
  const start = performance.now()
  const init: RequestInit = { method }
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = typeof body === 'string' ? body : JSON.stringify(body)
  }
  const resp = await fetch(`${BASE_URL}${path.replace(/^\//, '')}`, init)
  const ms = Math.round(performance.now() - start)
  let parsed: unknown
  const text = await resp.text()
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {
    parsed = text
  }
  return { status: resp.status, ok: resp.ok, ms, body: parsed }
}

export async function fetchHealth(): Promise<{ ok: boolean; body: unknown }> {
  const resp = await fetch(`${BASE_URL}health`)
  const body = await resp.json().catch(() => null)
  return { ok: resp.ok, body }
}

// Probes Fuseki reachability via the semantic endpoint: 200 = online,
// 503 (or any error) = offline.
export async function probeFuseki(): Promise<boolean> {
  try {
    const resp = await fetch(
      `${BASE_URL}api/v1/semantic?view=sensor-observations`,
    )
    return resp.ok
  } catch {
    return false
  }
}

export interface SystemStatus {
  healthOk: boolean
  fusekiOk: boolean
  deviceCount: number
  alertTotal: number
  recentCount: number
}

// Aggregates several read-only endpoints into one system snapshot used by
// SystemStatusView. Each probe is resilient: a failing call yields a safe
// default instead of rejecting the whole snapshot.
export async function fetchSystemStatus(): Promise<SystemStatus> {
  const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000)
  const [health, fusekiOk, devices, alerts, recent] = await Promise.all([
    fetchHealth().catch(() => ({ ok: false, body: null })),
    probeFuseki(),
    fetchDevices().catch(() => [] as string[]),
    fetchAlerts({ limit: 1 }).catch(() => ({ items: [], total: 0 })),
    fetchHistory({ since: tenMinAgo.toISOString(), limit: 1 }).catch(() => ({
      items: [],
      total: 0,
    })),
  ])
  return {
    healthOk: health.ok,
    fusekiOk,
    deviceCount: devices.length,
    alertTotal: alerts.total,
    recentCount: recent.total,
  }
}

// ---- Semantic gate & SPARQL (Phase: KG interactivity) ----------------

export interface GateStatus {
  status: 'passed' | 'rejected'
  checked_at: string
  last_device?: string
  reason?: string
  passed_count?: number
  rejected_count?: number
}

// Live SHACL gate status. Backend contract (to be implemented in
// backend/api/semantic.py, backed by observation_gate.py):
//   GET /api/v1/semantic/gate-status ->
//     { status, checked_at, last_device?, reason?, passed_count?, rejected_count? }
// Returns null when the endpoint is not yet available (404) so the UI can
// render a "pending integration" state instead of an error.
export async function fetchGateStatus(): Promise<GateStatus | null> {
  const resp = await fetch(`${BASE_URL}api/v1/semantic/gate-status`)
  if (resp.status === 404) return null
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export interface SparqlResult {
  columns: string[]
  rows: Array<Record<string, string>>
}

// Runs one of the named semantic views (GET /api/v1/semantic?view=X) and
// flattens the aggregated response into a tabular shape for display.
export async function runSemanticView(view: string): Promise<SparqlResult> {
  const data = await fetchSemanticView(view)
  const rows = data.results.map((r) => ({
    sensor: r.sensor,
    subsystem: r.subsystem,
    observes: r.observes.join(', '),
    protocol: r.protocol,
  }))
  return { columns: ['sensor', 'subsystem', 'observes', 'protocol'], rows }
}

// Custom SPARQL passthrough. Backend contract (proposed):
//   POST /api/v1/semantic/query  { "query": "<sparql>" }
//     -> SPARQL JSON results ({ head.vars, results.bindings })
// Throws with a descriptive message when the endpoint is missing so the
// panel can tell the user custom queries need backend integration.
export async function runSparqlQuery(query: string): Promise<SparqlResult> {
  const resp = await fetch(`${BASE_URL}api/v1/semantic/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  if (resp.status === 404 || resp.status === 405) {
    throw new Error('ENDPOINT_MISSING')
  }
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  const data = await resp.json()
  const vars: string[] = data?.head?.vars ?? []
  const bindings: Array<Record<string, { value: string }>> =
    data?.results?.bindings ?? []
  return {
    columns: vars,
    rows: bindings.map((b) =>
      Object.fromEntries(vars.map((v) => [v, b[v]?.value ?? ''])),
    ),
  }
}
