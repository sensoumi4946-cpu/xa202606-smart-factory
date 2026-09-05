#pragma once

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>

inline bool ensureWifi(const char* ssid, const char* password, uint32_t timeoutMs) {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.begin(ssid, password);
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < timeoutMs) {
    delay(100);
  }
  return WiFi.status() == WL_CONNECTED;
}

inline bool postObservation(const char* url, const char* apiKey, const String& json) {
  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client, url)) return false;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", apiKey);
  const int status = http.POST(json);
  http.end();
  return status >= 200 && status < 300;
}
