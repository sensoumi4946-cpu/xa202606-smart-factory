#include <ArduinoJson.h>
#include "device_config.h"
#include "../shared/rest_ingest.h"

uint32_t countValue = 0;
uint32_t lastTransitionMs = 0;
uint32_t lastReportMs = 0;
bool previousActive = false;

static String buildPayload() {
  JsonDocument doc;
  doc["schema_version"] = "v1";
  doc["device_id"] = DEVICE_ID;
  doc["subsystem"] = "counting";
  doc["protocol"] = "rest";
  JsonArray values = doc["measurements"].to<JsonArray>();
  JsonObject count = values.add<JsonObject>();
  count["type"] = "count";
  count["value"] = countValue;
  count["unit"] = "count";
  JsonObject raw = doc["raw_payload"].to<JsonObject>();
  raw["uptime_ms"] = millis();
  String output;
  serializeJson(doc, output);
  return output;
}

void setup() {
  Serial.begin(115200);
  pinMode(SENSOR_PIN, INPUT_PULLUP);
  previousActive = digitalRead(SENSOR_PIN) == ACTIVE_LEVEL;
  ensureWifi(WIFI_SSID, WIFI_PASS, WIFI_TIMEOUT_MS);
}

void loop() {
  const uint32_t now = millis();
  const bool active = digitalRead(SENSOR_PIN) == ACTIVE_LEVEL;
  if (active != previousActive && now - lastTransitionMs >= DEBOUNCE_MS) {
    lastTransitionMs = now;
    previousActive = active;
    if (active) countValue++;
  }
  if (now - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = now;
    if (ensureWifi(WIFI_SSID, WIFI_PASS, WIFI_TIMEOUT_MS)) {
      postObservation(INGEST_URL, API_KEY, buildPayload());
    }
  }
  delay(5);
}
