#pragma once

// Device configuration for the bench reference build. Do not place Wi-Fi
// passwords, HMAC keys, certificates, or vehicle credentials in this file.
// Provision those values into protected device storage in a production build.

#define INTERLOCK_DEVICE_ID "ESP32-BENCH-001"
#define INTERLOCK_VEHICLE_ID "BENCH-VEHICLE-001"

#define INTERLOCK_STATUS_LED_PIN 2
#define INTERLOCK_BUZZER_PIN 25
#define INTERLOCK_BENCH_OUTPUT_PIN 26
#define INTERLOCK_SENSOR_PIN 34
#define INTERLOCK_TEST_BUTTON_PIN 27

#define INTERLOCK_SAMPLE_COUNT 5
#define INTERLOCK_SENSOR_WARMUP_MS 30000UL
#define INTERLOCK_SAMPLE_INTERVAL_MS 250UL
#define INTERLOCK_TEST_INTERVAL_MS 5000UL
#define INTERLOCK_HEARTBEAT_INTERVAL_MS 30000UL
#define INTERLOCK_WATCHDOG_TIMEOUT_SECONDS 8

// This value is for bench-state demonstration only. It is not a BAC limit.
#define INTERLOCK_DEMO_THRESHOLD 0.02f

// The reference build must never be compiled as a direct automotive relay
// controller. A certified gateway is required for any vehicle integration.
#define INTERLOCK_BENCH_ONLY 1
