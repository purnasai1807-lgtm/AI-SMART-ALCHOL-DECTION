# Device simulator

Use `services.api.app.adapters.SimulatorAdapter` to generate signed readings
for the API. It deliberately models attestation, freshness, and nonce behavior
without pretending to be certified automotive hardware.

For a standalone JSON payload:

```sh
py -3 simulator/device_simulator.py --device-id 1 --vehicle-id 1 --secret "<secret>" --reading 0.01
```
