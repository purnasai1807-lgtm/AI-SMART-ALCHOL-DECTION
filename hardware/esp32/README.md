# ESP32 device abstraction

The production firmware should implement the `DeviceAdapter` contract in
`services/api/app/adapters.py` over a secure transport. Secrets belong in
ESP32 secure storage, never source control. The simulator is suitable for
local integration tests only; it does not control a vehicle.
