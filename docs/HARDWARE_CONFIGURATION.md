# Hardware configuration and bring-up

This procedure configures the **bench-safe ESP32 reference device** in this
repository. It does not certify an alcohol sensor and it does not connect a
vehicle starter, ignition, CAN bus, or relay. A production vehicle controller
must be designed and approved separately by an automotive safety/electrical
engineering team.

## 1. Parts and tools

- ESP32 DevKit board
- MQ-3 or equivalent prototype sensor for bench testing only
- 5 V regulated USB supply
- 3.3 V-safe ADC divider
- LED and 220 ohm resistor
- Transistor-driven active buzzer
- Optocoupler or isolated MOSFET module with an LED/dummy load
- Momentary push button
- PlatformIO Core
- USB data cable and serial monitor
- Multimeter; oscilloscope is recommended for output isolation testing

## 2. Wire the bench circuit

Power the ESP32 from USB. Connect the sensor, indicators, button, and isolated
dummy load exactly as shown below:

| Function | ESP32 | Bench connection |
|---|---:|---|
| Sensor analog output | GPIO34 | ADC divider, never above 3.3 V |
| Status LED | GPIO2 | 220 ohm resistor, then LED to GND |
| Buzzer control | GPIO25 | Transistor driver input |
| Dummy-load enable | GPIO26 | Optocoupler/MOSFET input only |
| Test button | GPIO27 | Momentary switch to GND |
| GPS UART (reserved) | GPIO16/17 | 3.3 V UART with level shifting |
| Ground | GND | Bench ground only |

Before powering the board, verify with a multimeter that GPIO34 cannot exceed
3.3 V and that the isolated output has no electrical continuity to vehicle
power. GPIO26 must drive an LED or resistor dummy load only.

## 3. Configure the device identity

Edit `hardware/esp32/include/hardware_config.h`:

```cpp
#define INTERLOCK_DEVICE_ID "ESP32-BENCH-001"
#define INTERLOCK_VEHICLE_ID "BENCH-VEHICLE-001"
```

Use a unique device ID for each physical board. The vehicle ID must match the
vehicle registered in the API. Do not put API secrets, Wi-Fi passwords, HMAC
keys, private keys, or certificates in this file or in source control. The
current firmware prints a signed-reading boundary demonstration; a production
transport must provision secrets into protected storage and use TLS.

The remaining values configure pins and timing:

- `INTERLOCK_SENSOR_WARMUP_MS`: sensor warm-up time.
- `INTERLOCK_SAMPLE_COUNT`: samples required for a test.
- `INTERLOCK_SAMPLE_INTERVAL_MS`: delay between samples.
- `INTERLOCK_DEMO_THRESHOLD`: bench normalized ADC threshold only.
- `INTERLOCK_BENCH_ONLY`: compile-time guard that must remain `1`.

Do not tune `INTERLOCK_DEMO_THRESHOLD` into a legal BAC claim. A certified
sensor driver must provide calibrated units and a reviewed policy.

## 4. Build and flash

From the repository root:

```sh
python -m pip install platformio
pio run -d hardware/esp32
pio run -d hardware/esp32 --target upload
pio device monitor -d hardware/esp32 -b 115200
```

On Windows, use `py -3 -m pip install platformio` if `python` is not on PATH.
Select the correct upload port when multiple USB devices are connected:

```sh
pio device list
pio run -d hardware/esp32 --target upload --upload-port COM5
```

Do not flash a board that is connected to a vehicle. Keep the dummy load
connected during bench testing.

## 5. Verify the state machine

After reset, the serial monitor must show:

1. `BOOTING`
2. `SELF_TEST`
3. `READY`
4. sensor warm-up
5. `TESTING` and `ANALYZING`
6. `SAFE` for a below-demo-threshold bench reading, or `BLOCKED`

Press the GPIO27 button to start a test. Confirm that:

- GPIO26 is low during boot, warm-up, error, blocked, and missing-sensor
  conditions.
- GPIO26 is high only temporarily in `SAFE`.
- Inconsistent samples produce `ERROR`.
- The buzzer is active for `BLOCKED` and `ERROR`.
- Heartbeats and JSON sensor events appear every 30 seconds/test.
- Resetting or unplugging the board leaves the dummy output deasserted.

## 6. Register the device in the API

Create the organization, vehicle, and device through the FastAPI service. Keep
the generated device secret in a deployment secret manager. The reference
firmware does not yet claim to be a complete Wi-Fi/TLS/HMAC transport; the
signed simulator and API contract are the integration reference:

```sh
python simulator/device_simulator.py \
  --device-id ESP32-BENCH-001 \
  --vehicle-id BENCH-VEHICLE-001 \
  --secret "<provisioned-device-secret>" \
  --reading 0.01
```

Use the API decision endpoint to validate nonce, timestamp, signature, device
pairing, and fail-secure behavior before connecting any future transport.

## 7. Production gate

The following are mandatory before a vehicle installation:

- Calibrated and certified alcohol sensor with traceable calibration records
- Automotive-rated power supply, isolation, enclosure, and connectors
- Secure boot, flash encryption, signed OTA, protected key provisioning
- Tamper switch and tamper-event reporting
- Hardware watchdog and brownout testing
- HIL tests for power loss, sensor failure, replay, network loss, and reset
- Certified gateway/ECU interface with an approved manual recovery policy
- Automotive functional-safety, cybersecurity, privacy, and regulatory review

No source change in this repository should bypass the `INTERLOCK_BENCH_ONLY`
guard or turn GPIO26 into a direct vehicle-control output.
