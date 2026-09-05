#include <ArduinoJson.h>
#include "device_config.h"
#include "../shared/rest_ingest.h"

uint32_t lastOccupiedMs = 0;
uint32_t lastReportMs = 0;
bool lightOn = false;

static void setLight(bool enabled) {
  lightOn = enabled;
  digitalWrite(RELAY_PIN, enabled ? RELAY_ON_LEVEL : !RELAY_ON_LEVEL);
}

static String buildPayload(bool occupied) {
  JsonDocument doc;
  doc["schema_version"] = "v1";
  doc["device_id"] = DEVICE_ID;
  doc["subsystem"] = "lighting";
  doc["protocol"] = "rest";
  JsonArray values = doc["measurements"].to<JsonArray>();
  JsonObject occupancy = values.add<JsonObject>();
  occupancy["type"] = "occupancy";
  occupancy["value"] = occupied ? 1.0 : 0.0;
  occupancy["unit"] = "boolean";
  JsonObject state = values.add<JsonObject>();
  state["type"] = "light_state";
  state["value"] = lightOn ? 1.0 : 0.0;
  state["unit"] = "boolean";
  JsonObject raw = doc["raw_payload"].to<JsonObject>();
  raw["uptime_ms"] = millis();
  String output;
  serializeJson(doc, output);
  return output;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  pinMode(RELAY_PIN, OUTPUT);
  setLight(false);
  ensureWifi(WIFI_SSID, WIFI_PASS, WIFI_TIMEOUT_MS);
}

void loop() {
  const uint32_t now = millis();
  const bool occupied = digitalRead(PIR_PIN) == HIGH;
  if (occupied) lastOccupiedMs = now;
  setLight(occupied || (lastOccupiedMs != 0 && now - lastOccupiedMs < HOLD_ON_MS));
  if (now - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = now;
    if (ensureWifi(WIFI_SSID, WIFI_PASS, WIFI_TIMEOUT_MS)) {
      postObservation(INGEST_URL, API_KEY, buildPayload(occupied));
    }
  }
  delay(20);
}
