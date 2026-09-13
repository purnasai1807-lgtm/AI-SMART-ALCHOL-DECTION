#include <Arduino.h>
#include <esp_task_wdt.h>

#include "../device_adapter.h"

// Bench-safe ESP32 reference firmware. GPIO26 is an isolated dummy-load
// signal only. A certified automotive gateway must enforce any real interlock.
enum class DeviceState {
  BOOTING,
  SELF_TEST,
  READY,
  TESTING,
  ANALYZING,
  SAFE,
  BLOCKED,
  ERROR,
  OFFLINE
};

constexpr uint8_t STATUS_LED_PIN = 2;
constexpr uint8_t BUZZER_PIN = 25;
constexpr uint8_t BENCH_OUTPUT_PIN = 26;
constexpr uint8_t SENSOR_PIN = 34;
constexpr uint8_t TEST_BUTTON_PIN = 27;
constexpr uint8_t SAMPLE_COUNT = 5;
constexpr uint32_t SENSOR_WARMUP_MS = 30000;
constexpr uint32_t SAMPLE_INTERVAL_MS = 250;
constexpr uint32_t TEST_INTERVAL_MS = 5000;
constexpr uint32_t HEARTBEAT_INTERVAL_MS = 30000;
constexpr uint32_t WATCHDOG_TIMEOUT_SECONDS = 8;
constexpr float DEMO_THRESHOLD = 0.02f;

DeviceState state = DeviceState::BOOTING;
uint32_t booted_at = 0;
uint32_t last_heartbeat = 0;
uint32_t next_test_at = 0;
uint32_t nonce_counter = 0;

const char *state_name(DeviceState value) {
  switch (value) {
    case DeviceState::BOOTING: return "BOOTING";
    case DeviceState::SELF_TEST: return "SELF_TEST";
    case DeviceState::READY: return "READY";
    case DeviceState::TESTING: return "TESTING";
    case DeviceState::ANALYZING: return "ANALYZING";
    case DeviceState::SAFE: return "SAFE";
    case DeviceState::BLOCKED: return "BLOCKED";
    case DeviceState::ERROR: return "ERROR";
    case DeviceState::OFFLINE: return "OFFLINE";
  }
  return "UNKNOWN";
}

void set_bench_output(bool enabled) {
  // Fail closed: every non-SAFE state deasserts the isolated output.
  digitalWrite(BENCH_OUTPUT_PIN, enabled ? HIGH : LOW);
}

void set_state(DeviceState next) {
  state = next;
  set_bench_output(state == DeviceState::SAFE);
  digitalWrite(STATUS_LED_PIN, state == DeviceState::SAFE ? HIGH : LOW);
  digitalWrite(BUZZER_PIN,
               state == DeviceState::BLOCKED || state == DeviceState::ERROR
                   ? HIGH
                   : LOW);
  Serial.printf("state=%s\n", state_name(state));
}

bool sensor_warmed() {
  return millis() - booted_at >= SENSOR_WARMUP_MS;
}

bool sensor_self_test() {
  pinMode(SENSOR_PIN, INPUT);
  const int first = analogRead(SENSOR_PIN);
  delay(20);
  const int second = analogRead(SENSOR_PIN);
  // An ADC stuck at either rail is treated as a sensor fault.
  return first > 8 && first < 4087 && second > 8 && second < 4087;
}

bool capture_samples(float *average) {
  if (!average || !sensor_warmed()) return false;
  float total = 0.0f;
  int minimum = 4095;
  int maximum = 0;
  for (uint8_t index = 0; index < SAMPLE_COUNT; ++index) {
    esp_task_wdt_reset();
    const int raw = analogRead(SENSOR_PIN);
    if (raw < 0 || raw > 4095) return false;
    minimum = min(minimum, raw);
    maximum = max(maximum, raw);
    total += static_cast<float>(raw) / 4095.0f;
    if (index + 1 < SAMPLE_COUNT) delay(SAMPLE_INTERVAL_MS);
  }
  // Excessive variance is unsafe to interpret as a negative test.
  if (maximum - minimum > 300) return false;
  *average = total / SAMPLE_COUNT;
  return true;
}

void emit_heartbeat() {
  last_heartbeat = millis();
  Serial.printf(
      "{\"type\":\"heartbeat\",\"state\":\"%s\",\"uptime_ms\":%lu,"
      "\"nonce_counter\":%lu}\n",
      state_name(state), static_cast<unsigned long>(millis()),
      static_cast<unsigned long>(nonce_counter));
}

void perform_test() {
  set_state(DeviceState::TESTING);
  float reading = 0.0f;
  const bool captured = capture_samples(&reading);
  set_state(DeviceState::ANALYZING);
  ++nonce_counter;
  if (!captured) {
    set_state(DeviceState::ERROR);
    Serial.println("{\"type\":\"decision\",\"decision\":\"ERROR\","
                   "\"reason\":\"sensor_unavailable_or_inconsistent\"}");
    next_test_at = millis() + TEST_INTERVAL_MS;
    return;
  }

  // This is only a bench indication. The cloud's authenticated policy is
  // authoritative and a calibrated sensor is required for any deployment.
  const bool below_demo_threshold = reading < DEMO_THRESHOLD;
  set_state(below_demo_threshold ? DeviceState::SAFE : DeviceState::BLOCKED);
  Serial.printf(
      "{\"type\":\"sensor_reading\",\"reading\":%.6f,\"nonce\":%lu,"
      "\"decision\":\"%s\"}\n",
      reading, static_cast<unsigned long>(nonce_counter),
      below_demo_threshold ? "ALLOW" : "BLOCK");
  next_test_at = millis() + TEST_INTERVAL_MS;
}

void setup() {
  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(BENCH_OUTPUT_PIN, OUTPUT);
  pinMode(TEST_BUTTON_PIN, INPUT_PULLUP);
  set_bench_output(false);
  Serial.begin(115200);
  booted_at = millis();
  esp_task_wdt_init(WATCHDOG_TIMEOUT_SECONDS, true);
  esp_task_wdt_add(NULL);
  set_state(DeviceState::BOOTING);
  delay(250);
  set_state(DeviceState::SELF_TEST);
  if (!sensor_self_test()) {
    set_state(DeviceState::ERROR);
  } else {
    set_state(DeviceState::READY);
  }
  next_test_at = millis() + SENSOR_WARMUP_MS;
}

void loop() {
  esp_task_wdt_reset();
  const uint32_t now = millis();
  if (now - last_heartbeat >= HEARTBEAT_INTERVAL_MS) emit_heartbeat();

  if (state == DeviceState::ERROR || state == DeviceState::OFFLINE) {
    set_bench_output(false);
    delay(100);
    return;
  }

  const bool button_pressed = digitalRead(TEST_BUTTON_PIN) == LOW;
  if (button_pressed || (state == DeviceState::READY && now >= next_test_at)) {
    perform_test();
  }
  if (state == DeviceState::SAFE && now >= next_test_at) {
    set_state(DeviceState::READY);
  }
  delay(20);
}
