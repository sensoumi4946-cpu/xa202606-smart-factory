#include <WiFi.h>
#include <ModbusIP_ESP8266.h>
#include "device_config.h"

// Zero-based offsets corresponding to declared addresses 40003, 40005, 40007,
// and 40009 with registerBase=40001 in bindings.ttl.
static const uint16_t REG_SMOKE = 2;
static const uint16_t REG_COMBUSTIBLE_GAS = 4;
static const uint16_t REG_CO = 6;
static const uint16_t REG_STATUS = 8;
static const uint16_t STATUS_NORMAL = 0;
static const uint16_t STATUS_CALIBRATION_REQUIRED = 4;

ModbusIP modbus;
uint32_t lastSampleMs = 0;

static bool ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < WIFI_TIMEOUT_MS) {
    delay(100);
  }
  return WiFi.status() == WL_CONNECTED;
}

static float resistanceKohm(uint16_t adc) {
  if (adc == 0 || adc >= ADC_MAX) return NAN;
  return LOAD_RESISTANCE_KOHM * (ADC_MAX - adc) / adc;
}

static float ppm(float resistance, float r0, float a, float b) {
  if (!isfinite(resistance) || r0 <= 0.0f) return NAN;
  return a * powf(resistance / r0, b);
}

static void writeFloat32(uint16_t offset, float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  modbus.Hreg(offset, static_cast<uint16_t>(bits >> 16));
  modbus.Hreg(offset + 1, static_cast<uint16_t>(bits & 0xffff));
}

void setup() {
  Serial.begin(115200);
  ensureWifi();
  modbus.server();
  for (uint16_t offset = REG_SMOKE; offset <= REG_STATUS; offset++) {
    modbus.addHreg(offset, 0);
  }
}

void loop() {
  ensureWifi();
  modbus.task();
  const uint32_t now = millis();
  if (now - lastSampleMs < SAMPLE_INTERVAL_MS) return;
  lastSampleMs = now;

  if (MQ2_R0_KOHM <= 0.0f || MQ7_R0_KOHM <= 0.0f) {
    modbus.Hreg(REG_STATUS, STATUS_CALIBRATION_REQUIRED);
    return;
  }

  const float mq2Resistance = resistanceKohm(analogRead(MQ2_PIN));
  const float mq7Resistance = resistanceKohm(analogRead(MQ7_PIN));
  const float smoke = ppm(mq2Resistance, MQ2_R0_KOHM, MQ2_SMOKE_A, MQ2_SMOKE_B);
  const float combustible = ppm(mq2Resistance, MQ2_R0_KOHM, MQ2_GAS_A, MQ2_GAS_B);
  const float co = ppm(mq7Resistance, MQ7_R0_KOHM, MQ7_CO_A, MQ7_CO_B);
  if (!isfinite(smoke) || !isfinite(combustible) || !isfinite(co)) {
    modbus.Hreg(REG_STATUS, STATUS_CALIBRATION_REQUIRED);
    return;
  }
  writeFloat32(REG_SMOKE, smoke);
  writeFloat32(REG_COMBUSTIBLE_GAS, combustible);
  writeFloat32(REG_CO, co);
  modbus.Hreg(REG_STATUS, STATUS_NORMAL);
}
