import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockChart = {
  setOption: vi.fn(),
  dispose: vi.fn(),
  on: vi.fn(),
  resize: vi.fn(),
  getDom: vi.fn(),
}
vi.mock('echarts', () => ({ init: vi.fn(() => mockChart) }))

vi.mock('../src/api', () => ({
  fetchLatest: vi.fn().mockResolvedValue([]),
  fetchLatestDeduped: vi.fn().mockResolvedValue([]),
  fetchHistory: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchAlerts: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchDevices: vi.fn().mockResolvedValue(['sensor_dht22_01', 'sensor_mq2_01']),
  fetchDeviceData: vi.fn().mockResolvedValue([]),
  fetchAllData: vi.fn().mockResolvedValue([]),
  fetchSemanticView: vi.fn().mockResolvedValue({
    view: 'sensor-observations',
    description: 'All sensors',
    results: [],
  }),
  fetchSystemStatus: vi.fn().mockResolvedValue({
    healthOk: true,
    fusekiOk: true,
    deviceCount: 5,
    alertTotal: 3,
    recentCount: 1200,
  }),
  probeFuseki: vi.fn().mockResolvedValue(true),
  fetchHealth: vi.fn().mockResolvedValue({ ok: true, body: { status: 'ok' } }),
  rawRequest: vi
    .fn()
    .mockResolvedValue({ status: 200, ok: true, ms: 5, body: { pong: true } }),
}))

afterEach(() => {
  vi.clearAllMocks()
})

import ConsoleLayout from '../src/layouts/ConsoleLayout.vue'
import StatusBar from '../src/components/StatusBar.vue'
import DashboardView from '../src/views/DashboardView.vue'
import ApiConsoleView from '../src/views/ApiConsoleView.vue'
import DeviceManagerView from '../src/views/DeviceManagerView.vue'
import SystemStatusView from '../src/views/SystemStatusView.vue'

describe('ConsoleLayout', () => {
  it('renders four tabs and switches the active tab on click', async () => {
    const wrapper = mount(ConsoleLayout, {
      props: { active: 'monitor' },
      slots: { default: '<div class="stub-view">view</div>' },
    })
    const tabs = wrapper.findAll('.tab')
    expect(tabs).toHaveLength(4)
    expect(wrapper.find('.tab.active').text()).toBe('监控')
    await tabs[1].trigger('click')
    expect(wrapper.emitted('update:active')?.[0]).toEqual(['console'])
  })
})

describe('StatusBar', () => {
  it('renders adapter lamps and counts', async () => {
    const wrapper = mount(StatusBar)
    await flushPromises()
    expect(wrapper.text()).toContain('MQTT')
    expect(wrapper.text()).toContain('Fuseki')
    expect(wrapper.findAll('.lamp')).toHaveLength(5)
  })
})

describe('DashboardView', () => {
  it('renders protocol-badged panel cards', () => {
    const wrapper = mount(DashboardView)
    expect(wrapper.findAll('.card').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('MQTT')
  })
})

describe('ApiConsoleView', () => {
  it('lists endpoints, selects one, and sends showing a response', async () => {
    const wrapper = mount(ApiConsoleView)
    const eps = wrapper.findAll('.ep')
    expect(eps).toHaveLength(8)
    await eps[1].trigger('click')
    expect(wrapper.find('.url').text()).toContain('/api/v1/latest')
    await wrapper.find('.send').trigger('click')
    await flushPromises()
    const api = await import('../api')
    expect(vi.mocked(api.rawRequest)).toHaveBeenCalled()
    expect(wrapper.find('.code').text()).toBe('200')
  })
})

describe('DeviceManagerView', () => {
  it('renders a device row per returned id', async () => {
    const wrapper = mount(DeviceManagerView)
    await flushPromises()
    expect(wrapper.text()).toContain('sensor_dht22_01')
    expect(wrapper.findAll('tbody tr').length).toBeGreaterThan(0)
  })
})

describe('SystemStatusView', () => {
  it('renders health and throughput cards', async () => {
    const wrapper = mount(SystemStatusView)
    await flushPromises()
    expect(wrapper.text()).toContain('API 健康')
    expect(wrapper.text()).toContain('数据吞吐')
  })
})
