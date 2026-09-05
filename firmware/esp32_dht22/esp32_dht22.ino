#include <WiFi.h>
#include <PubSubClient.h>
#include <esp_task_wdt.h>
#include <time.h>
#include <mbedtls/md.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include "device_config.h"
#include "sensor_dht22.h"

enum DeviceStatus : uint16_t {
  DEV_NORMAL = 0,
  DEV_STARTING = 1,
  DEV_DEGRADED = 2,
  DEV_FAULT = 3,
  DEV_MAINTENANCE = 4
};

enum ErrorCode : uint16_t {
  ERR_NONE = 0,
  ERR_READ_TIMEOUT = 1,
  ERR_CHECKSUM = 2,
  ERR_WIFI_LOST = 3,
  ERR_LOW_VOLTAGE = 4
};

enum SensorStatus : uint16_t {
  SEN_OK = 0,
  SEN_WARMING_UP = 1,
  SEN_DRIFTING = 2,
  SEN_DISCONNECTED = 3,
  SEN_OUT_OF_RANGE = 4
};

struct Reading {
  uint32_t epoch;
  float temperature;
  float humidity;
  bool valid;
};

struct RingBuffer {
  Reading slots[RING_CAPACITY];
  uint16_t head = 0;
  uint16_t count = 0;

  void push(const Reading& r) {
    slots[head] = r;
    head = (head + 1) % RING_CAPACITY;
    if (count < RING_CAPACITY) count++;
  }

  bool pop(Reading& out) {
    if (count == 0) return false;
    uint16_t tail = (head + RING_CAPACITY - count) % RING_CAPACITY;
    out = slots[tail];
    count--;
    return true;
  }

  bool full() const { return count >= RING_CAPACITY; }
  uint16_t size() const { return count; }
};

WiFiClient netClient;
PubSubClient mqtt(netClient);
RingBuffer buffer;

uint16_t deviceStatus = DEV_STARTING;
uint16_t errorCode = ERR_NONE;
uint16_t sensorStatus = SEN_WARMING_UP;

uint32_t lastPublish = 0;
uint32_t lastHeartbeat = 0;
bool timeSynced = false;
bool failSafeEngaged = false;

char recentNonces[64][25] = {};
uint32_t nonceTimes[64] = {};
uint8_t nonceCursor = 0;

static void applyFailSafe(const char* reason) {
  if (!failSafeEngaged) {
    digitalWrite(RELAY_PIN, RELAY_DE_ENERGISED);
    failSafeEngaged = true;
    Serial.printf("[failsafe] de-energised: %s\n", reason);
  }
}

static void releaseFailSafe() {
  if (failSafeEngaged) {
    failSafeEngaged = false;
    Serial.println("[failsafe] link restored");
  }
}

static uint32_t nowEpoch() {
  time_t t = time(nullptr);
  return (t > 1600000000UL) ? (uint32_t)t : 0;
}

static void syncTime() {
  configTime(0, 0, NTP_1, NTP_2);
  uint32_t deadline = millis() + 10000;
  while (millis() < deadline) {
    if (nowEpoch() > 0) {
      timeSynced = true;
      Serial.printf("[time] synced: %lu\n", (unsigned long)nowEpoch());
      return;
    }
    delay(200);
    esp_task_wdt_reset();
  }
  timeSynced = false;
  Serial.println("[time] NTP sync failed, timestamps will be omitted");
}

static void toHex(const uint8_t* data, size_t len, char* out) {
  static const char* digits = "0123456789abcdef";
  for (size_t i = 0; i < len; i++) {
    out[i * 2] = digits[data[i] >> 4];
    out[i * 2 + 1] = digits[data[i] & 0x0F];
  }
  out[len * 2] = '\0';
}

static void hmacSha256(const char* key, const char* msg, char* hexOut) {
  uint8_t digest[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const uint8_t*)key, strlen(key));
  mbedtls_md_hmac_update(&ctx, (const uint8_t*)msg, strlen(msg));
  mbedtls_md_hmac_finish(&ctx, digest);
  mbedtls_md_free(&ctx);
  toHex(digest, 32, hexOut);
}

static bool verifyCommand(JsonDocument& doc) {
  const char* sig = doc["signature"] | "";
  const char* nonce = doc["nonce"] | "";
  const char* issuedAt = doc["issued_at"] | "";

  if (strlen(sig) == 0 || strlen(nonce) == 0) {
    Serial.println("[cmd] rejected: unsigned");
    return false;
  }
  if (strcmp(doc["device_id"] | "", DEVICE_ID) != 0 || strlen(nonce) != 24 || !timeSynced) return false;
  for (uint8_t i = 0; i < 64; i++) {
    if (strcmp(nonce, recentNonces[i]) == 0) return false;
  }

  char paramsJson[192];
  serializeJson(doc["params"], paramsJson, sizeof(paramsJson));

  char canonical[576];
  snprintf(canonical, sizeof(canonical),
           "%s|%s|%s|%s|%s|%s",
           doc["command_id"] | "",
           doc["device_id"] | "",
           doc["action"] | "",
           paramsJson,
           issuedAt,
           nonce);

  char expected[65];
  hmacSha256(SIGNING_KEY, canonical, expected);

  if (strcmp(expected, sig) != 0) {
    Serial.println("[cmd] rejected: bad signature");
    return false;
  }

  if (strlen(issuedAt) < 20) return false;
  struct tm tmv = {};
  if (strptime(issuedAt, "%Y-%m-%dT%H:%M:%S", &tmv) == nullptr) return false;
  const size_t stampLength = strlen(issuedAt);
  if (issuedAt[stampLength - 1] != 'Z' && (stampLength < 6 || strcmp(issuedAt + stampLength - 6, "+00:00") != 0)) return false;
  const time_t issued = mktime(&tmv);
  const time_t current = nowEpoch();
  if (llabs((long long)current - issued) > MAX_CLOCK_SKEW_S) return false;
  if (recentNonces[nonceCursor][0] && current <= nonceTimes[nonceCursor] + MAX_CLOCK_SKEW_S * 2) return false;
  strncpy(recentNonces[nonceCursor], nonce, 24);
  recentNonces[nonceCursor][24] = '\0';
  nonceTimes[nonceCursor] = current;
  nonceCursor = (nonceCursor + 1) % 64;
  return true;
}

static bool readSensor(Reading& out) {
  float t = readTemperature();
  float h = readHumidity();

  if (isnan(t) || isnan(h)) {
    sensorStatus = SEN_DISCONNECTED;
    errorCode = ERR_READ_TIMEOUT;
    out.valid = false;
    return false;
  }
  if (t < -40.0f || t > 80.0f || h < 0.0f || h > 100.0f) {
    sensorStatus = SEN_OUT_OF_RANGE;
    out.valid = false;
    return false;
  }

  if (sensorStatus == SEN_DISCONNECTED || sensorStatus == SEN_OUT_OF_RANGE) {
    sensorStatus = SEN_OK;
    errorCode = ERR_NONE;
  }

  out.epoch = nowEpoch();
  out.temperature = t;
  out.humidity = h;
  out.valid = true;
  return true;
}

static void buildPayload(const Reading& r, char* out, size_t len) {
  JsonDocument doc;
  doc["schema_version"] = "v1";
  doc["device_id"] = DEVICE_ID;
  doc["subsystem"] = SUBSYSTEM;
  doc["protocol"] = "mqtt";
  if (r.epoch > 0) {
    time_t epoch = r.epoch;
    struct tm utc;
    gmtime_r(&epoch, &utc);
    char stamp[24];
    strftime(stamp, sizeof(stamp), "%Y-%m-%dT%H:%M:%SZ", &utc);
    doc["timestamp"] = stamp;
  }
  JsonArray values = doc["measurements"].to<JsonArray>();
  JsonObject temperature = values.add<JsonObject>();
  temperature["type"] = "temperature";
  temperature["value"] = r.temperature;
  temperature["unit"] = "celsius";
  JsonObject humidity = values.add<JsonObject>();
  humidity["type"] = "humidity";
  humidity["value"] = r.humidity;
  humidity["unit"] = "percent";
  const char* names[] = {"device_status", "error_code", "sensor_status"};
  uint16_t statuses[] = {deviceStatus, errorCode, sensorStatus};
  for (uint8_t i = 0; i < 3; i++) {
    JsonObject status = values.add<JsonObject>();
    status["type"] = names[i];
    status["value"] = statuses[i];
    status["unit"] = "status";
  }
  doc["raw_payload"]["buffered"] = buffer.size();
  serializeJson(doc, out, len);
}

static bool publish(const Reading& r) {
  if (!mqtt.connected()) return false;
  char topic[128];
  snprintf(topic, sizeof(topic), "factory/%s/sensors/%s/reading",
           SUBSYSTEM, DEVICE_ID);
  char payload[1024];
  buildPayload(r, payload, sizeof(payload));
  return mqtt.publish(topic, payload);
}

static void drainBuffer() {
  uint8_t sent = 0;
  Reading r;
  while (sent < BACKFILL_PER_CYCLE && mqtt.connected() && buffer.pop(r)) {
    if (!publish(r)) {
      buffer.push(r);
      break;
    }
    sent++;
    esp_task_wdt_reset();
  }
  if (sent > 0) Serial.printf("[buffer] backfilled %u readings\n", sent);
}

static void onCommand(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<512> doc;
  if (deserializeJson(doc, payload, length) != DeserializationError::Ok) return;

  if (!verifyCommand(doc)) return;
  lastHeartbeat = millis();
  releaseFailSafe();
  const char* action = doc["action"] | "";
  if (strcmp(action, "heartbeat") == 0) return;
  if (strcmp(action, "on") == 0) {
    digitalWrite(RELAY_PIN, HIGH);
  } else if (strcmp(action, "off") == 0 || strcmp(action, "close") == 0) {
    digitalWrite(RELAY_PIN, RELAY_DE_ENERGISED);
  } else if (strcmp(action, "toggle") == 0) {
    digitalWrite(RELAY_PIN, !digitalRead(RELAY_PIN));
  } else {
    Serial.printf("[cmd] unsupported action %s\n", action);
    return;
  }
  Serial.printf("[cmd] executed %s\n", action);
}

static void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t deadline = millis() + 8000;
  while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
    delay(250);
    esp_task_wdt_reset();
  }
  if (WiFi.status() != WL_CONNECTED) {
    errorCode = ERR_WIFI_LOST;
    deviceStatus = DEV_DEGRADED;
  } else {
    if (errorCode == ERR_WIFI_LOST) errorCode = ERR_NONE;
    if (!timeSynced) syncTime();
  }
}

static void connectMqtt() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  if (mqtt.connect(DEVICE_ID)) {
    char topic[128];
    snprintf(topic, sizeof(topic), "factory/%s/control/%s", SUBSYSTEM, DEVICE_ID);
    mqtt.subscribe(topic, 1);
    lastHeartbeat = millis();
    Serial.println("[mqtt] connected");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, RELAY_DE_ENERGISED);

  deviceStatus = DEV_STARTING;
  sensorStatus = SEN_WARMING_UP;

  esp_task_wdt_config_t wdt = {
      .timeout_ms = WDT_TIMEOUT_S * 1000,
      .idle_core_mask = 0,
      .trigger_panic = true,
  };
  esp_task_wdt_init(&wdt);
  esp_task_wdt_add(NULL);

  initSensor();
  sensorStatus = SEN_OK;
  deviceStatus = DEV_NORMAL;
  connectWifi();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onCommand);
  mqtt.setBufferSize(1024);
  connectMqtt();
}

void loop() {
  esp_task_wdt_reset();

  connectWifi();
  connectMqtt();
  mqtt.loop();

  if (millis() - lastHeartbeat > HEARTBEAT_TIMEOUT_MS) {
    applyFailSafe("no platform heartbeat");
  }

  if (millis() - lastPublish >= PUBLISH_INTERVAL_MS) {
    lastPublish = millis();

    Reading r;
    if (readSensor(r)) {
      if (mqtt.connected() && buffer.size() == 0) {
        if (!publish(r)) buffer.push(r);
      } else {
        if (buffer.full()) {
          Reading discarded;
          buffer.pop(discarded);
        }
        buffer.push(r);
      }
    }
  }

  if (mqtt.connected() && buffer.size() > 0) {
    drainBuffer();
  }

  delay(20);
}
