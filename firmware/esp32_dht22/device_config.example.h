#pragma once

static const char* WIFI_SSID = "your-factory-ap";
static const char* WIFI_PASS = "replace-with-device-secret";
static const char* MQTT_HOST = "192.0.2.10";
static const uint16_t MQTT_PORT = 1883;
static const char* DEVICE_ID = "ESP32_001_dht22";
static const char* SUBSYSTEM = "temp_humidity";
static const char* SIGNING_KEY = "replace-with-command-signing-key";

static const char* NTP_1 = "ntp.aliyun.com";
static const char* NTP_2 = "cn.pool.ntp.org";

static const uint8_t DHT_PIN = 4;
static const uint8_t DHT_TYPE = DHT22;
static const uint8_t RELAY_PIN = 26;
static const uint8_t RELAY_DE_ENERGISED = LOW;
static const uint32_t PUBLISH_INTERVAL_MS = 2000;
static const uint32_t HEARTBEAT_TIMEOUT_MS = 15000;
static const uint32_t MAX_CLOCK_SKEW_S = 30;
static const uint32_t WDT_TIMEOUT_S = 30;
static const uint16_t RING_CAPACITY = 200;
static const uint8_t BACKFILL_PER_CYCLE = 10;
static const uint8_t DHT_MAX_RETRIES = 3;
