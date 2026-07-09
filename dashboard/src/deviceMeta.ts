// Static device metadata shared by StatusBar, DeviceManager and detail
// drawers. Maps each known device id to its protocol, subsystem and the
// concrete access path (MQTT topic / REST endpoint / Modbus register /
// OPC UA node). Kept as a frontend constant because the backend API does
// not expose this wiring.
export interface DeviceMeta {
  protocol: string
  subsystem: string
  connectVia: string
}

export const DEVICE_META: Record<string, DeviceMeta> = {
  sensor_dht22_01: {
    protocol: 'mqtt',
    subsystem: 'temp_humidity',
    connectVia: 'factory/temp_humidity/sensors/sensor_dht22_01/...',
  },
  sensor_pir_01: {
    protocol: 'rest',
    subsystem: 'lighting',
    connectVia: 'POST /adapter/rest/ingest (lighting vendor JSON)',
  },
  sensor_mq2_01: {
    protocol: 'modbus',
    subsystem: 'gas',
    connectVia: 'holding registers [0-2] (zero-based)',
  },
  sensor_hcsr04_01: {
    protocol: 'opcua',
    subsystem: 'agv',
    connectVia: 'ns=2;s=distance (subscription)',
  },
  sensor_ir_01: {
    protocol: 'rest',
    subsystem: 'counting',
    connectVia: 'POST /adapter/rest/ingest (compact payload)',
  },
}

// Uppercase protocol label for badges (mqtt -> MQTT, opcua -> OPC UA).
export function protoLabel(proto: string): string {
  if (proto === 'opcua') return 'OPC UA'
  return proto.toUpperCase()
}
