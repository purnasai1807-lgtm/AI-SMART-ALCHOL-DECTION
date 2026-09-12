#pragma once

#include <stdbool.h>

// Hardware boundary: implementations must return a monotonic nonce and a
// signed reading, while failing closed when the sensor or clock is unavailable.
typedef struct {
  const char *device_id;
  const char *vehicle_id;
  float reading;
  const char *nonce;
  const char *signature;
} interlock_reading_t;

bool interlock_read(interlock_reading_t *out);
