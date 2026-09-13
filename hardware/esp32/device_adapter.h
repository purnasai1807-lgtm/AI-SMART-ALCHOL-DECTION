#pragma once

#include <stdbool.h>
#include <stdint.h>

// Hardware boundary: implementations must return a monotonic nonce and a
// signed reading, while failing closed when the sensor or clock is unavailable.
typedef struct {
  const char *device_id;
  const char *vehicle_id;
  float reading;
  const char *nonce;
  const char *signature;
} interlock_reading_t;

typedef enum {
  INTERLOCK_SENSOR_OK = 0,
  INTERLOCK_SENSOR_WARMING,
  INTERLOCK_SENSOR_FAULT,
  INTERLOCK_SENSOR_UNCALIBRATED
} interlock_sensor_status_t;

typedef struct {
  interlock_sensor_status_t status;
  float normalized_reading;
  uint16_t sample_count;
  uint32_t captured_at_ms;
} interlock_sensor_sample_t;

// Implementations must never map an unavailable or uncalibrated sensor to a
// negative alcohol result. The cloud service remains the policy authority.
bool interlock_read(interlock_reading_t *out);
bool interlock_sensor_sample(interlock_sensor_sample_t *out);
