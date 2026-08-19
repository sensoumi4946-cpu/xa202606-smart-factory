// Regression tests for the dashboard bugs


import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { isReactive, nextTick } from 'vue'

vi.mock('../api', () => ({
  fetchDeviceRegistry: vi.fn(),
  fetchLatestDeduped: vi.fn(),
  fetchAlerts: vi.fn(),
  rawRequest: vi.fn(),
}))

import { fetchDeviceRegistry, fetchLatestDeduped, rawRequest } from '../api'
import { DEVICE_META, refreshDeviceMeta, protoLabel, subsystemLabel } from '../deviceMeta'
import DeviceManagerView from '../views/DeviceManagerView.vue'
import SensorGauge from '../components/SensorGauge.vue'

const REGISTRY = [
  {
    device_id: 'esp32_01_dht22',
    subsystem: 'temp_humidity',
    protocol: 'mqtt',
    last_seen: new Date().toISOString(),
  },
  {
    device_id: 'esp32_02_mq2',
    subsystem: 'gas',
    protocol: 'modbus',
    last_seen: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
  },
]

function latestFor(deviceId: string, ageMs: number) {
  return [
    {
      device_id: deviceId,
      subsystem: 'temp_humidity',
      measurements: [
        {
          type: 'temperature',
          value: 26.1,
          unit: 'celsius',
          timestamp: new Date(Date.now() - ageMs).toISOString(),
        },
      ],
    },
  ]
}

beforeEach(() => {
  for (const k of Object.keys(DEVICE_META)) delete DEVICE_META[k]
  vi.mocked(fetchDeviceRegistry).mockResolvedValue(REGISTRY as never)
  vi.mocked(fetchLatestDeduped).mockResolvedValue([] as never)
  vi.mocked(rawRequest).mockResolvedValue({
    status: 202,
    ok: true,
    ms: 5,
    body: { command_id: 'abcdef123456', status: 'dispatched' },
  } as never)
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('deviceMeta', () => {
  it('is reactive so computed properties re-run after load', () => {
    // Was a plain object; components never re-rendered when it filled in.
    expect(isReactive(DEVICE_META)).toBe(true)
  })

  it('populates from the registry', async () => {
    await refreshDeviceMeta()
    expect(DEVICE_META['esp32_01_dht22'].protocol).toBe('mqtt')
    expect(DEVICE_META['esp32_02_mq2'].subsystem).toBe('gas')
  })

  it('survives a failing registry call without throwing', async () => {
    vi.mocked(fetchDeviceRegistry).mockRejectedValue(new Error('offline'))
    await expect(refreshDeviceMeta()).resolves.toBeUndefined()
    expect(Object.keys(DEVICE_META)).toHaveLength(0)
  })

  it('renders protocol labels rather than raw keys', () => {
    expect(protoLabel('opcua')).toBe('OPC UA')
    expect(protoLabel('mqtt')).toBe('MQTT')
    expect(protoLabel(undefined)).toBe('--')
  })

  it('renders Chinese subsystem labels', () => {
    expect(subsystemLabel('temp_humidity')).toBe('温湿度')
    expect(subsystemLabel('agv')).toBe('AGV 避障')
    expect(subsystemLabel(undefined)).toBe('--')
  })
})

describe('DeviceManagerView', () => {
  it('shows the protocol instead of a dash once the registry loads', async () => {
    const w = mount(DeviceManagerView)
    await flush()
    const text = w.text()
    expect(text).toContain('MQTT')
    expect(text).toContain('MODBUS')
    w.unmount()
  })

  it('lists devices that are in the registry but absent from /latest', async () => {
    vi.mocked(fetchLatestDeduped).mockResolvedValue([] as never)
    const w = mount(DeviceManagerView)
    await flush()
    expect(w.text()).toContain('esp32_01_dht22')
    expect(w.text()).toContain('esp32_02_mq2')
    w.unmount()
  })

  it('marks a device online when its newest reading is recent', async () => {
    vi.mocked(fetchLatestDeduped).mockResolvedValue(
      latestFor('esp32_01_dht22', 5_000) as never,
    )
    const w = mount(DeviceManagerView)
    await flush()
    expect(w.text()).toContain('在线')
    w.unmount()
  })

  it('marks a device offline when its newest reading is stale', async () => {
    vi.mocked(fetchLatestDeduped).mockResolvedValue(
      latestFor('esp32_01_dht22', 10 * 60 * 1000) as never,
    )
    const w = mount(DeviceManagerView)
    await flush()
    expect(w.text()).toContain('离线')
    w.unmount()
  })

  it('sends a real control command when 开启 is clicked', async () => {
    const w = mount(DeviceManagerView)
    await flush()
    const btn = w.findAll('button').find((b) => b.text() === '开启')
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    await flush()
    expect(rawRequest).toHaveBeenCalledWith(
      'POST',
      '/api/v1/control',
      expect.objectContaining({ action: 'on' }),
    )
    w.unmount()
  })

  it('reports a failed control command instead of failing silently', async () => {
    vi.mocked(rawRequest).mockResolvedValue({
      status: 500,
      ok: false,
      ms: 5,
      body: null,
    } as never)
    const w = mount(DeviceManagerView)
    await flush()
    const btn = w.findAll('button').find((b) => b.text() === '开启')
    await btn!.trigger('click')
    await flush()
    expect(w.text()).toContain('下发失败')
    w.unmount()
  })
})

describe('SensorGauge', () => {
  it('renders the value', () => {
    const w = mount(SensorGauge, {
      props: { label: 'CO', value: 12.3, unit: 'ppm', max: 50 },
    })
    expect(w.text()).toContain('12.3')
    w.unmount()
  })

  it('shows a dash when there is no reading', () => {
    const w = mount(SensorGauge, { props: { label: 'CO', value: null } })
    expect(w.text()).toContain('--')
    w.unmount()
  })

  it('turns danger when a high-direction value passes the danger line', () => {
    const w = mount(SensorGauge, {
      props: { label: 'CO', value: 90, max: 100, warn: 35, danger: 60 },
    })
    expect(w.find('.num').classes()).toContain('danger')
    w.unmount()
  })

  it('turns danger when a low-direction value drops below the danger line', () => {
    // Distance is inverted — small is bad. A gauge that only understands
    // "high is bad" would show AGV collisions as healthy.
    const w = mount(SensorGauge, {
      props: {
        label: '距离',
        value: 10,
        max: 200,
        warn: 30,
        danger: 15,
        direction: 'low',
      },
    })
    expect(w.find('.num').classes()).toContain('danger')
    w.unmount()
  })

  it('stays ok for a safe low-direction value', () => {
    const w = mount(SensorGauge, {
      props: {
        label: '距离',
        value: 180,
        max: 200,
        warn: 30,
        danger: 15,
        direction: 'low',
      },
    })
    expect(w.find('.num').classes()).not.toContain('danger')
    w.unmount()
  })

  it('clamps a value above max without breaking the arc', () => {
    const w = mount(SensorGauge, {
      props: { label: 'CO', value: 5000, max: 100, danger: 60 },
    })
    const d = w.find('.value').attributes('d') ?? ''
    expect(d).not.toContain('NaN')
    w.unmount()
  })

  it('does not divide by zero when min equals max', () => {
    const w = mount(SensorGauge, {
      props: { label: 'X', value: 5, min: 10, max: 10 },
    })
    expect(w.html()).not.toContain('NaN')
    w.unmount()
  })
})

async function flush() {
  await nextTick()
  await Promise.resolve()
  await new Promise((r) => setTimeout(r, 0))
  await nextTick()
}
