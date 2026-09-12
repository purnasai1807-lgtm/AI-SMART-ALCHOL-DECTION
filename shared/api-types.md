# Shared API types

The safety contract is intentionally transport-neutral. A sensor POST contains
`device_id`, `vehicle_id`, non-negative `reading`, UTC `timestamp`, single-use
`nonce`, and an HMAC-SHA256 `signature`. The canonical signed value is
`device_id.vehicle_id.nonce.timestamp.reading`. Decisions are `UNLOCKED` only
for valid, fresh, non-replayed attestations below the configured threshold;
every failure is persisted as `LOCKED`.
