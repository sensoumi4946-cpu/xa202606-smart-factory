#include <WiFi.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <esp_task_wdt.h>
#include <time.h>
#include <mbedtls/md.h>
#include <ArduinoJson.h>

static const char* WIFI_SSID = "FACTORY_AP";
static const char* WIFI_PASS = "changeme";
static const char* MQTT_HOST = "192.168.1.50";
static const uint16_t MQTT_PORT = 1883;
static const char* DEVICE_ID = "ESP32_001_dht22";
static const char* SUBSYSTEM = "temp_humidity";
static const char* SIGNING_KEY = "ce30c115aec4ca7be413779292ea725c0f323afff4ab9d70e4e946e46a6a4460";

static const char* NTP_1 = "ntp.aliyun.com";
static const char* NTP_2 = "cn.pool.ntp.org";

static const uint32_t WDT_TIMEOUT_S = 30;
static const uint32_t PUBLISH_INTERVAL_MS = 2000;
static const uint32_t HEARTBEAT_TIMEOUT_MS = 15000;
static const uint32_t MAX_CLOCK_SKEW_S = 30;

static const uint16_t RING_CAPACITY = 200;
static const uint8_t BACKFILL_PER_CYCLE = 10;

static const uint32_t MQ2_BURN_IN_MS = 180000UL;
static const uint32_t MQ2_RECALIBRATION_INTERVAL_S = 2592000UL;

static const uint8_t RELAY_PIN = 26;
static const uint8_t RELAY_DE_ENERGISED = LOW;

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
  ERR_LOW_VOLTAGE = 4,
  ERR_CALIBRATION_DUE = 5
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
Preferences prefs;
RingBuffer buffer;

uint16_t deviceStatus = DEV_STARTING;
uint16_t errorCode = ERR_NONE;
uint16_t sensorStatus = SEN_WARMING_UP;

uint32_t bootMillis = 0;
uint32_t lastPublish = 0;
uint32_t lastHeartbeat = 0;
bool timeSynced = false;
bool failSafeEngaged = false;

float mq2R0 = 0.0f;
uint32_t mq2CalibratedAt = 0;

char lastNonce[24] = {0};

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
  configTime(8 * 3600, 0, NTP_1, NTP_2);
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
  if (strcmp(nonce, lastNonce) == 0) {
    Serial.println("[cmd] rejected: nonce replay");
    return false;
  }

  char canonical[384];
  snprintf(canonical, sizeof(canonical),
           "%s|%s|%s|%s|%s",
           doc["command_id"] | "",
           doc["device_id"] | "",
           doc["action"] | "",
           issuedAt,
           nonce);

  char expected[65];
  hmacSha256(SIGNING_KEY, canonical, expected);

  if (strcmp(expected, sig) != 0) {
    Serial.println("[cmd] rejected: bad signature");
    return false;
  }

  if (timeSynced && strlen(issuedAt) >= 19) {
    struct tm tmv = {0};
    if (strptime(issuedAt, "%Y-%m-%dT%H:%M:%S", &tmv) != nullptr) {
      uint32_t issued = (uint32_t)mktime(&tmv);
      uint32_t current = nowEpoch();
      uint32_t skew = (current > issued) ? (current - issued) : (issued - current);
      if (skew > MAX_CLOCK_SKEW_S) {
        Serial.printf("[cmd] rejected: stale by %lus\n", (unsigned long)skew);
        return false;
      }
    }
  }

  strncpy(lastNonce, nonce, sizeof(lastNonce) - 1);
  return true;
}

static void calibrateMq2() {
  prefs.begin("cal", false);
  mq2R0 = prefs.getFloat("mq2_r0", 0.0f);
  mq2CalibratedAt = prefs.getUInt("mq2_at", 0);
  prefs.end();

  uint32_t current = nowEpoch();
  bool due = (mq2R0 <= 0.0f) ||
             (current > 0 && mq2CalibratedAt > 0 &&
              (current - mq2CalibratedAt) > MQ2_RECALIBRATION_INTERVAL_S);

  if (due) {
    errorCode = ERR_CALIBRATION_DUE;
    Serial.println("[cal] MQ-2 calibration due");
  }
}

static void finishBurnIn() {
  if (sensorStatus == SEN_WARMING_UP && millis() - bootMillis > MQ2_BURN_IN_MS) {
    sensorStatus = SEN_OK;
    deviceStatus = DEV_NORMAL;
    Serial.println("[cal] burn-in complete, readings now trusted");
  }
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
  snprintf(out, len,
           "{\"schema_version\":\"v1\",\"device_id\":\"%s\",\"subsystem\":\"%s\","
           "\"protocol\":\"mqtt\",\"measurements\":["
           "{\"type\":\"temperature\",\"value\":%.1f,\"unit\":\"celsius\"},"
           "{\"type\":\"humidity\",\"value\":%.1f,\"unit\":\"percent\"}],"
           "\"device_status\":%u,\"error_code\":%u,\"sensor_status\":%u,"
           "\"buffered\":%u}",
           DEVICE_ID, SUBSYSTEM, r.temperature, r.humidity,
           deviceStatus, errorCode, sensorStatus, buffer.size());
}

static bool publish(const Reading& r) {
  if (!mqtt.connected()) return false;
  char topic[128];
  snprintf(topic, sizeof(topic), "factory/%s/sensors/%s/reading",
           SUBSYSTEM, DEVICE_ID);
  char payload[512];
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

  lastHeartbeat = millis();

  const char* type = doc["type"] | "";
  if (strcmp(type, "heartbeat") == 0) {
    releaseFailSafe();
    return;
  }

  if (!verifyCommand(doc)) return;

  const char* action = doc["action"] | "";
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

  bootMillis = millis();
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
  connectWifi();
  calibrateMq2();

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

  finishBurnIn();

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
