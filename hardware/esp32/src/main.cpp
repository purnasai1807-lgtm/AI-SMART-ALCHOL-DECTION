#include <Arduino.h>

// Bench-safe ESP32 reference firmware. It demonstrates the device state
// machine and fail-closed output boundary; it does not drive a vehicle relay.
enum class DeviceState {
  BOOTING, READY, AUTHENTICATING, TEST_REQUIRED, TESTING,
  ANALYZING, SAFE, UNSAFE, BLOCKED, EMERGENCY, OFFLINE, ERROR
};

constexpr uint8_t STATUS_LED_PIN = 2;
constexpr uint8_t BUZZER_PIN = 25;
constexpr uint8_t BENCH_OUTPUT_PIN = 26;
constexpr uint8_t SENSOR_PIN = 34;

DeviceState state = DeviceState::BOOTING;
unsigned long lastHeartbeat = 0;

void setState(DeviceState next) {
  state = next;
  // SAFE is the only state that may assert the bench output. In production,
  // this signal must terminate at a certified gateway, never a starter relay.
  digitalWrite(BENCH_OUTPUT_PIN, state == DeviceState::SAFE ? HIGH : LOW);
  digitalWrite(STATUS_LED_PIN, state == DeviceState::SAFE ? HIGH : LOW);
  digitalWrite(BUZZER_PIN, state == DeviceState::BLOCKED || state == DeviceState::ERROR ? HIGH : LOW);
}

float readPrototypeSensor() {
  // Replace with a calibrated sensor driver. Raw MQ-3 voltage is not BAC.
  return static_cast<float>(analogRead(SENSOR_PIN)) / 4095.0f;
}

void setup() {
  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(BENCH_OUTPUT_PIN, OUTPUT);
  pinMode(SENSOR_PIN, INPUT);
  Serial.begin(115200);
  setState(DeviceState::BOOTING);
  delay(500);
  setState(DeviceState::READY);
}

void loop() {
  if (millis() - lastHeartbeat > 30000) {
    lastHeartbeat = millis();
    // Production implementation sends signed heartbeat over TLS.
    Serial.println("heartbeat: device-ready");
  }

  if (state == DeviceState::READY || state == DeviceState::TEST_REQUIRED) {
    setState(DeviceState::TESTING);
    const float sample = readPrototypeSensor();
    delay(250);
    setState(DeviceState::ANALYZING);
    // This is a bench-only threshold demonstration. Cloud policy is
    // authoritative in the real integration.
    setState(sample < 0.02f ? DeviceState::SAFE : DeviceState::BLOCKED);
    Serial.printf("bench sample=%.4f state=%s\n", sample,
                  state == DeviceState::SAFE ? "SAFE" : "BLOCKED");
    delay(5000);
    setState(DeviceState::TEST_REQUIRED);
  }
}
