#pragma once

static const char* WIFI_SSID = "your-factory-ap";
static const char* WIFI_PASS = "replace-with-device-secret";
static const char* INGEST_URL = "http://192.0.2.10:8000/ingest/api/v1/data";
static const char* API_KEY = "replace-with-api-key";
static const char* DEVICE_ID = "ESP32_002";
static const uint8_t SENSOR_PIN = 27;
static const uint8_t ACTIVE_LEVEL = LOW;
static const uint32_t DEBOUNCE_MS = 80;
static const uint32_t REPORT_INTERVAL_MS = 2000;
static const uint32_t WIFI_TIMEOUT_MS = 8000;
