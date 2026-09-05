#pragma once

#include <Arduino.h>
#include <DHT.h>

static DHT _dht(DHT_PIN, DHT_TYPE);
static uint32_t _lastRead = 0;
static float _cachedTemperature = NAN;
static float _cachedHumidity = NAN;

inline void initSensor() {
  _dht.begin();
  delay(2000);
  _cachedTemperature = _dht.readTemperature();
  _cachedHumidity = _dht.readHumidity();
}

inline void _refresh() {
  if (millis() - _lastRead < PUBLISH_INTERVAL_MS) return;
  _lastRead = millis();

  for (uint8_t attempt = 0; attempt < DHT_MAX_RETRIES; attempt++) {
    float t = _dht.readTemperature();
    float h = _dht.readHumidity();
    if (!isnan(t) && !isnan(h)) {
      _cachedTemperature = t;
      _cachedHumidity = h;
      return;
    }
    delay(50);
  }
  _cachedTemperature = NAN;
  _cachedHumidity = NAN;
}

inline float readTemperature() {
  _refresh();
  return _cachedTemperature;
}

inline float readHumidity() {
  _refresh();
  return _cachedHumidity;
}
