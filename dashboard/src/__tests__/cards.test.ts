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

vi.mock('../api', () => ({
  fetchDeviceData: vi.fn().mockResolvedValue([
    {
      id: 'r1',
      device_id: 'sensor_dht22_01',
      subsystem: 'temp_humidity',
      protocol: 'mqtt',
      timestamp: '2026-07-09T10:00:00Z',
      measurements: [{ type: 'temperature', value: 24, unit: 'celsius' }],
    },
    {
      id: 'r2',
      device_id: 'sensor_dht22_01',
      subsystem: 'temp_humidity',
      protocol: 'mqtt',
      timestamp: '2026-07-09T10:01:00Z',
      measurements: [{ type: 'temperature', value: 25, unit: 'celsius' }],
    },
  ]),
}))

afterEach(() => {
  vi.clearAllMocks()
})

import DeviceCard from '../components/DeviceCard.vue'
import MiniChart from '../components/MiniChart.vue'
import DeviceDrawer from '../components/DeviceDrawer.vue'

describe('DeviceCard', () => {
  it('renders a protocol badge and emits open with the device id', async () => {
    const wrapper = mount(DeviceCard, {
      props: { deviceId: 'sensor_mq2_01', protocol: 'modbus' },
      slots: { default: '<div class="inner">panel</div>' },
    })
    expect(wrapper.find('.badge').text()).toBe('MODBUS')
    expect(wrapper.find('.card.tappable').exists()).toBe(true)
    await wrapper.find('.card').trigger('click')
    expect(wrapper.emitted('open')?.[0]).toEqual(['sensor_mq2_01'])
  })

  it('does not emit or mark tappable when clickable is false', async () => {
    const wrapper = mount(DeviceCard, {
      props: { clickable: false },
      slots: { default: '<div>info</div>' },
    })
    expect(wrapper.find('.card.tappable').exists()).toBe(false)
    await wrapper.find('.card').trigger('click')
    expect(wrapper.emitted('open')).toBeUndefined()
  })
})

describe('MiniChart', () => {
  it('mounts a chart container and pushes options', async () => {
    const wrapper = mount(MiniChart, {
      props: {
        label: 'temperature',
        unit: 'celsius',
        points: [
          { t: '2026-07-09T10:00:00Z', v: 24 },
          { t: '2026-07-09T10:01:00Z', v: 25 },
        ],
      },
    })
    expect(wrapper.find('.mini').exists()).toBe(true)
    expect(mockChart.setOption).toHaveBeenCalled()
  })
})

describe('DeviceDrawer', () => {
  it('renders a mini chart per measurement type and toggles raw JSON', async () => {
    const wrapper = mount(DeviceDrawer, {
      props: { deviceId: 'sensor_dht22_01' },
    })
    await flushPromises()
    expect(wrapper.findComponent(MiniChart).exists()).toBe(true)
    await wrapper.find('.toggle').trigger('click')
    expect(wrapper.find('.json').exists()).toBe(true)
  })
})
