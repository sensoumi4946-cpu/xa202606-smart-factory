#pragma once

static const char* WIFI_SSID = "your-factory-ap";
static const char* WIFI_PASS = "replace-with-device-secret";
static const uint8_t MQ2_PIN = 34;
static const uint8_t MQ7_PIN = 35;
static const uint32_t SAMPLE_INTERVAL_MS = 2000;
static const uint32_t WIFI_TIMEOUT_MS = 8000;
static const float ADC_MAX = 4095.0f;
static const float LOAD_RESISTANCE_KOHM = 10.0f;

// Replace with values obtained from clean-air calibration and the exact sensor
// datasheet/batch. The firmware refuses to publish when either R0 is invalid.
static const float MQ2_R0_KOHM = 0.0f;
static const float MQ7_R0_KOHM = 0.0f;
static const float MQ2_SMOKE_A = 36974.0f;
static const float MQ2_SMOKE_B = -3.109f;
static const float MQ2_GAS_A = 574.25f;
static const float MQ2_GAS_B = -2.222f;
static const float MQ7_CO_A = 99.042f;
static const float MQ7_CO_B = -1.518f;
