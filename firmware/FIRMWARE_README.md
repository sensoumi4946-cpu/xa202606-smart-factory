# ESP32 firmware

## Libraries (Arduino IDE → 库管理器)
- `DHT sensor library` by Adafruit
- `Adafruit Unified Sensor`
- `PubSubClient` by Nick O'Leary
- `ArduinoJson` (v7)

Board: **ESP32 Dev Module**, partition scheme default.

## Wiring
| Signal | GPIO |
|---|---|
| DHT22 data | 4 (10k pull-up to 3V3) |
| Relay | 26 |

## Before flashing
Set these at the top of `esp32_dht22.ino`:

```
WIFI_SSID, WIFI_PASS      your AP
MQTT_HOST                 the PC running the backend
DEVICE_ID                 one id per sensor, not per board
SIGNING_KEY               must equal COMMAND_SIGNING_KEY in deploy/.env
```

## What the firmware does beyond reading a sensor
- 200-reading ring buffer; on reconnect it backfills 10 per cycle
- 30s task watchdog
- NTP against `ntp.aliyun.com`, used for command freshness, not for stamping data
- MQ-2 burn-in state; readings marked untrusted for the first 3 minutes
- HMAC-SHA256 signature + nonce on every incoming command
- 15s deadman: relay de-energises when platform heartbeats stop

## Fail-safe wiring
The de-energised state differs per actuator and must be wired to match:

| Device | Relay type | De-energised |
|---|---|---|
| 燃气主阀 | normally closed | closed |
| 排风机 | normally open, on UPS | running |
| 照明 | normally open | on |

Getting this backwards is worse than having no fail-safe at all.
