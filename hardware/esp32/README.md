# ESP32 device application

This directory contains a **bench-safe ESP32 reference application** and the
hardware abstraction used by the cloud simulator. It demonstrates the device
state machine, sensor input, status indicators, heartbeat boundary, and
fail-closed output behavior. It is not a certified breathalyzer or automotive
immobilizer controller.

For the complete assembly, configuration, flashing, verification, and
production-gate procedure, see `docs/HARDWARE_CONFIGURATION.md`.

## Hardware bill of materials

- ESP32 DevKit board with secure boot/flash encryption enabled for production
- MQ-3 or equivalent prototype alcohol sensor module for bench experiments only
- NEO-6M or equivalent GPS module for location integration
- Active buzzer and red/green LEDs with current-limiting resistors
- Optocoupler or isolated MOSFET module connected to a **dummy load/LED**
- 5 V regulated supply and 3.3 V level-safe wiring
- Enclosure, tamper switch, and watchdog-capable power path for field hardware
- Momentary test button with internal pull-up

## Bench wiring

| Signal | ESP32 pin | Connection |
|---|---:|---|
| Prototype sensor analog output | GPIO34 (ADC) | Sensor output through a 3.3 V-safe divider |
| Green status LED | GPIO2 | 220 ohm resistor to LED, then GND |
| Buzzer | GPIO25 | Transistor driver; do not drive a large buzzer directly |
| Isolated bench output | GPIO26 | Optocoupler/MOSFET to LED or dummy load only |
| Test button | GPIO27 | Momentary switch to GND; starts a local bench test |
| GPS TX/RX | UART2 GPIO16/17 | 3.3 V UART; level-shift 5 V modules |
| Common ground | GND | Bench common ground; isolate vehicle power |

Never connect GPIO26 to a starter motor, ignition circuit, CAN bus, or vehicle
relay. A production vehicle path requires a separately certified gateway with
electrical isolation, secure boot, signed firmware, watchdog recovery, manual
override policy, tamper evidence, and legal approval.

## Flashing

Install PlatformIO, set the board in `platformio.ini`, then run:

```sh
pio run
pio run --target upload
pio device monitor
```

The firmware waits for sensor warm-up, performs a five-sample consistency check,
uses a watchdog, emits JSON heartbeat/reading events, and prints state
transitions over serial. A failed self-test, unavailable sensor, inconsistent
samples, watchdog reset, or any state other than `SAFE` deasserts GPIO26.
Replace the prototype sensor driver and cloud transport only after calibration,
secure provisioning, TLS certificate validation, and hardware safety review.

## Hardware state machine

`BOOTING -> SELF_TEST -> READY -> TESTING -> ANALYZING -> SAFE/BLOCKED`.
`SAFE` is temporary and returns to `READY`; `BLOCKED` and `ERROR` keep the
bench output low. The firmware never treats a missing, warming, noisy, or
out-of-range sensor as a negative result.

For production, enable ESP32 secure boot and flash encryption, store the device
identity in eFuse-backed or equivalent protected storage, sign OTA images, add
tamper detection, and replace the demo threshold with a calibrated sensor
driver and server-signed policy. These controls require hardware provisioning
and validation outside this repository.

The production firmware should implement the `DeviceAdapter` contract in
`services/api/app/adapters.py` over a secure transport. Secrets belong in
ESP32 secure storage, never source control. The simulator is suitable for
local integration tests only; it does not control a vehicle.
