// ============================================================
// Demo mode (?demo=1): intercepts /api/v1/* and /health fetches
// and serves generated sample data, including a cross-subsystem
// "fire risk" scenario (temperature + CO rising together).
//
// Purpose: design review and stage demos without a running
// backend. Remove the query param to talk to the real API.
// This file monkey-patches window.fetch and is imported from
// main.ts only when the flag is present.
// ============================================================

const DEVICES = [
  'sensor_dht22_01',
  'sensor_pir_01',
  'sensor_mq2_01',
  'sensor_hcsr04_01',
  'sensor_ir_01',
]

// Scenario clock: everything is derived from seconds since page load.
const t0 = Date.now()
const elapsed = () => (Date.now() - t0) / 1000

// Fire scenario: normal for 20s, then temp & CO climb, critical after ~35s.
function tempValue(): number {
  const e = elapsed()
  const base = 24 + Math.sin(e / 7) * 0.8
  if (e < 20) return round(base)
  return round(Math.min(base + (e - 20) * 1.6, 78))
}
function humidityValue(): number {
  return round(48 + Math.sin(elapsed() / 11) * 4)
}
function coValue(): number {
  const e = elapsed()
  const base = 18 + Math.sin(e / 5) * 3
  if (e < 24) return round(base)
  return round(Math.min(base + (e - 24) * 14, 420))
}
function smokeValue(): number {
  const e = elapsed()
  return round(e < 24 ? 6 : Math.min(6 + (e - 24) * 3, 90))
}
function distValue(): number {
  return round(120 + Math.sin(elapsed() / 3) * 60)
}
function countValue(): number {
  return Math.floor(elapsed() / 4)
}
function round(v: number): number {
  return Math.round(v * 10) / 10
}

const fireActive = () => tempValue() > 45 && coValue() > 200

function nowIso(offsetSec = 0): string {
  return new Date(Date.now() - offsetSec * 1000).toISOString()
}

function latestPayload() {
  return [
    {
      device_id: 'sensor_dht22_01',
      subsystem: 'temp_humidity',
      measurements: [
        { type: 'temperature', value: tempValue(), unit: '°C', timestamp: nowIso() },
        { type: 'humidity', value: humidityValue(), unit: '%', timestamp: nowIso() },
      ],
    },
    {
      device_id: 'sensor_mq2_01',
      subsystem: 'gas',
      measurements: [
        { type: 'co_concentration', value: coValue(), unit: 'ppm', timestamp: nowIso() },
        { type: 'smoke_level', value: smokeValue(), unit: '%', timestamp: nowIso() },
      ],
    },
    {
      device_id: 'sensor_hcsr04_01',
      subsystem: 'agv',
      measurements: [
        { type: 'distance', value: distValue(), unit: 'cm', timestamp: nowIso() },
      ],
    },
    {
      device_id: 'sensor_pir_01',
      subsystem: 'lighting',
      measurements: [
        { type: 'motion', value: Math.sin(elapsed() / 9) > 0 ? 1 : 0, unit: 'bool', timestamp: nowIso() },
      ],
    },
    {
      device_id: 'sensor_ir_01',
      subsystem: 'counting',
      measurements: [
        { type: 'count', value: countValue(), unit: 'items', timestamp: nowIso() },
      ],
    },
  ]
}

let alertSeq = 0
interface DemoAlert {
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
const alertLog: DemoAlert[] = []

function pushAlert(a: Omit<DemoAlert, 'id' | 'source_record_id' | 'triggered_at'>) {
  alertLog.unshift({
    ...a,
    id: `demo-alert-${++alertSeq}`,
    source_record_id: `demo-rec-${alertSeq}`,
    triggered_at: nowIso(),
  })
  if (alertLog.length > 40) alertLog.pop()
}

let lastAlertTick = 0
function tickAlerts() {
  const e = elapsed()
  if (e - lastAlertTick < 4) return
  lastAlertTick = e
  const temp = tempValue()
  const co = coValue()
  if (temp > 60) {
    pushAlert({
      rule_name: 'temp_hard_limit',
      level: 'critical',
      device_id: 'sensor_dht22_01',
      subsystem: 'temp_humidity',
      measurement_type: 'temperature',
      value: temp,
      threshold: 60,
      message: `温度超过硬性阈值: ${temp}°C > 60°C`,
    })
  } else if (temp > 40) {
    pushAlert({
      rule_name: 'temp_zscore',
      level: 'warning',
      device_id: 'sensor_dht22_01',
      subsystem: 'temp_humidity',
      measurement_type: 'temperature',
      value: temp,
      threshold: 40,
      message: `温度异常上升 (Z-score): ${temp}°C`,
    })
  }
  if (co > 200) {
    pushAlert({
      rule_name: 'co_hard_limit',
      level: 'critical',
      device_id: 'sensor_mq2_01',
      subsystem: 'gas',
      measurement_type: 'co_concentration',
      value: co,
      threshold: 200,
      message: `CO 浓度超过硬性阈值: ${co} ppm > 200 ppm`,
    })
  } else if (co > 80) {
    pushAlert({
      rule_name: 'co_zscore',
      level: 'warning',
      device_id: 'sensor_mq2_01',
      subsystem: 'gas',
      measurement_type: 'co_concentration',
      value: co,
      threshold: 80,
      message: `CO 浓度异常上升 (Z-score): ${co} ppm`,
    })
  }
  if (fireActive() && !alertLog.some((a) => a.rule_name === 'cross_fire_risk' && Date.now() - new Date(a.triggered_at).getTime() < 15000)) {
    pushAlert({
      rule_name: 'cross_fire_risk',
      level: 'critical',
      device_id: 'sensor_dht22_01+sensor_mq2_01',
      subsystem: 'cross_subsystem',
      measurement_type: 'fire_risk',
      value: co,
      threshold: 200,
      message: '跨子系统关联: 温度与CO同时异常 — 疑似火灾风险 (10s 窗口)',
    })
  }
}

function historyPayload(deviceId?: string) {
  const items = []
  for (let i = 0; i < 30; i++) {
    const dev = deviceId ?? DEVICES[i % DEVICES.length]
    items.push({
      id: `demo-hist-${i}`,
      device_id: dev,
      subsystem: dev.includes('mq2') ? 'gas' : dev.includes('dht') ? 'temp_humidity' : 'other',
      protocol: dev.includes('dht') ? 'mqtt' : dev.includes('mq2') ? 'modbus' : dev.includes('hcsr') ? 'opcua' : 'rest',
      timestamp: nowIso(i * 5),
      measurements: [
        { type: 'temperature', value: round(24 + Math.sin(i / 3) * 2), unit: '°C' },
      ],
    })
  }
  return { items, total: items.length }
}

const semanticPayload = {
  view: 'sensor-observations',
  description: 'Sensors and the observable properties they observe (demo)',
  results: [
    { sensor: 'sensor_dht22_01', subsystem: 'temp_humidity', observes: ['temperature', 'humidity'], protocol: 'mqtt' },
    { sensor: 'sensor_mq2_01', subsystem: 'gas', observes: ['co_concentration', 'smoke_level'], protocol: 'modbus' },
    { sensor: 'sensor_hcsr04_01', subsystem: 'agv', observes: ['distance'], protocol: 'opcua' },
    { sensor: 'sensor_pir_01', subsystem: 'lighting', observes: ['motion'], protocol: 'rest' },
    { sensor: 'sensor_ir_01', subsystem: 'counting', observes: ['count'], protocol: 'rest' },
  ],
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function installDemoMode(): void {
  const realFetch = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = url.replace(/^https?:\/\/[^/]+/, '')

    tickAlerts()

    if (path.startsWith('/health')) {
      return json({ status: 'ok', demo: true })
    }
    if (path.startsWith('/api/v1/latest')) {
      const m = /device_id=([^&]+)/.exec(path)
      const all = latestPayload()
      return json(m ? all.filter((d) => d.device_id === decodeURIComponent(m[1])) : all)
    }
    if (path.startsWith('/api/v1/devices')) {
      return json(DEVICES)
    }
    if (path.startsWith('/api/v1/alerts')) {
      const lvl = /level=([^&]+)/.exec(path)?.[1]
      const items = lvl ? alertLog.filter((a) => a.level === lvl) : alertLog
      const limit = Number(/limit=(\d+)/.exec(path)?.[1] ?? 20)
      return json({ items: items.slice(0, limit), total: items.length })
    }
    if (path.startsWith('/api/v1/history')) {
      const m = /device_id=([^&]+)/.exec(path)
      return json(historyPayload(m ? decodeURIComponent(m[1]) : undefined))
    }
    if (path.startsWith('/api/v1/data')) {
      const m = /device_id=([^&]+)/.exec(path)
      return json(historyPayload(m ? decodeURIComponent(m[1]) : undefined).items)
    }
    if (path.startsWith('/api/v1/semantic/gate-status')) {
      // Scenario: gate passes normally; one demo REJECTED event at ~30-36s
      // (an observation missing its unit, refused by observation_shapes.ttl).
      const e = elapsed()
      const rejected = e > 30 && e < 36
      return json({
        status: rejected ? 'rejected' : 'passed',
        checked_at: nowIso(),
        last_device: rejected ? 'sensor_mq2_01' : 'sensor_dht22_01',
        reason: rejected ? '观测缺少计量单位 (sosa:hasResult/unit)' : undefined,
        passed_count: Math.floor(e * 2.4),
        rejected_count: e > 36 ? 1 : rejected ? 1 : 0,
      })
    }
    if (path.startsWith('/api/v1/semantic/query')) {
      // Custom SPARQL passthrough (demo): returns SPARQL JSON results built
      // from the same fixture; a query mentioning measuresCO/Temperature
      // narrows to the fire-correlation pair.
      let bodyText = ''
      try {
        bodyText = init?.body ? String(init.body) : ''
      } catch {
        /* ignore */
      }
      const narrow = /measuresCO|measuresTemperature/.test(bodyText)
      const rows = semanticPayload.results.filter(
        (r) => !narrow || ['temp_humidity', 'gas'].includes(r.subsystem),
      )
      const vars = ['sensor', 'subsystem', 'protocol', 'prop']
      const bindings = rows.flatMap((r) =>
        r.observes.map((p) => ({
          sensor: { value: r.sensor },
          subsystem: { value: r.subsystem },
          protocol: { value: r.protocol },
          prop: { value: p },
        })),
      )
      return json({ head: { vars }, results: { bindings } })
    }
    if (path.startsWith('/api/v1/semantic/fire-risk')) {
      return json({ risk_detected: fireActive() })
    }
    if (path.startsWith('/api/v1/semantic')) {
      return json(semanticPayload)
    }
    return realFetch(input as RequestInfo, init)
  }
  console.info('[demo] Demo mode active — API calls are simulated. Remove ?demo=1 to use the real backend.')
}
