# Hardware boundary

`hardware/esp32/device_adapter.h` defines the replaceable adapter boundary.
`simulator/` exercises signed readings without pretending to be a certified
breathalyzer.

A production device needs secure provisioning, unique credentials, secure boot,
signed OTA firmware, watchdog recovery, calibration records, tamper evidence,
GPS and heartbeat reporting, offline behavior, and a separately validated
vehicle gateway. Never connect prototype MQ-3 output or browser code directly
to a starter relay.

