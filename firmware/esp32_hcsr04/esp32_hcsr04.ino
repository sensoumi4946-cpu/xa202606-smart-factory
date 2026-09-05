#include <ArduinoJson.h>
#include "device_config.h"

uint32_t lastSampleMs = 0;

static float readDistanceCm() {
  digitalWrite(TRIGGER_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIGGER_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIGGER_PIN, LOW);
  const uint32_t duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (duration == 0) return NAN;
  return duration * SOUND_SPEED_CM_PER_US / 2.0f;
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
}

void loop() {
  if (millis() - lastSampleMs < SAMPLE_INTERVAL_MS) return;
  lastSampleMs = millis();
  const float distance = readDistanceCm();
  if (isnan(distance)) return;
  JsonDocument doc;
  doc["distance"] = distance;
  doc["uptime_ms"] = millis();
  serializeJson(doc, Serial);
  Serial.println();
}
