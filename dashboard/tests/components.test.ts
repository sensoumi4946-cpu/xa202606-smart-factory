import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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
  fetchHistory: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchAlerts: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchDevices: vi.fn().mockResolvedValue([]),
  fetchDeviceData: vi.fn().mockResolvedValue([]),
  fetchAllData: vi.fn().mockResolvedValue([]),
  fetchSemanticView: vi.fn().mockResolvedValue({
    view: 'sensor-observations',
    description: 'All sensors',
    results: [
      { sensor: 'sensor_dht22_01', subsystem: 'temp_humidity', observes: ['temperature'], protocol: 'mqtt' },
    ],
  }),
}))

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

import TempGauge from '../src/components/TempGauge.vue'
import GasMonitor from '../src/components/GasMonitor.vue'
import AgvTrack from '../src/components/AgvTrack.vue'
import CountBar from '../src/components/CountBar.vue'
import LightingPanel from '../src/components/LightingPanel.vue'
import AlertsPanel from '../src/components/AlertsPanel.vue'
import HistoryTable from '../src/components/HistoryTable.vue'
import SemanticPanel from '../src/components/SemanticPanel.vue'

describe('component smoke tests', () => {
  it('TempGauge renders title and chart container', () => {
    const wrapper = mount(TempGauge, { global: { stubs: { } } })
    expect(wrapper.text()).toContain('温湿度监测')
    expect(wrapper.find('.chart').exists()).toBe(true)
  })

  it('GasMonitor renders title and chart container', () => {
    const wrapper = mount(GasMonitor, { global: { stubs: { } } })
    expect(wrapper.text()).toContain('气体浓度监测')
    expect(wrapper.find('.chart').exists()).toBe(true)
  })

  it('AgvTrack renders title and chart container', () => {
    const wrapper = mount(AgvTrack, { global: { stubs: { } } })
    expect(wrapper.text()).toContain('AGV 避障距离')
    expect(wrapper.find('.chart').exists()).toBe(true)
  })

  it('CountBar renders title and chart container', () => {
    const wrapper = mount(CountBar, { global: { stubs: { } } })
    expect(wrapper.text()).toContain('货物感应计数')
    expect(wrapper.find('.chart').exists()).toBe(true)
  })

  it('LightingPanel renders title and status grid', () => {
    const wrapper = mount(LightingPanel, { global: { stubs: { } } })
    expect(wrapper.text()).toContain('照明状态')
    expect(wrapper.find('.status-grid').exists()).toBe(true)
  })

  it('AlertsPanel renders title and empty placeholder', () => {
    const wrapper = mount(AlertsPanel, { global: { stubs: { } } })
    expect(wrapper.text()).toContain('告警面板')
  })

  it('HistoryTable renders title and controls', () => {
    const wrapper = mount(HistoryTable, { global: { stubs: { } } })
    expect(wrapper.text()).toContain('历史查询')
    expect(wrapper.find('.controls').exists()).toBe(true)
  })

  it('SemanticPanel renders title', () => {
    const wrapper = mount(SemanticPanel, { global: { stubs: { } } })
    expect(wrapper.text()).toContain('语义关联')
  })
})

describe('SemanticPanel state handling', () => {
  it('shows error text when the semantic service is unavailable', async () => {
    const api = await import('../src/api')
    vi.mocked(api.fetchSemanticView).mockRejectedValueOnce(new Error('down'))
    const wrapper = mount(SemanticPanel, { global: { stubs: { } } })
    await flushPromises()
    expect(wrapper.text()).toContain('语义服务不可用')
  })

  it('shows empty hint when no semantic rows are returned', async () => {
    const api = await import('../src/api')
    vi.mocked(api.fetchSemanticView).mockResolvedValueOnce({
      view: 'sensor-observations',
      description: 'none',
      results: [],
    })
    const wrapper = mount(SemanticPanel, { global: { stubs: { } } })
    await flushPromises()
    expect(wrapper.text()).toContain('暂无语义数据')
  })
})
