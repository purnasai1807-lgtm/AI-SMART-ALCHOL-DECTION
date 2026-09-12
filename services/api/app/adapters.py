"""Stable contracts for physical devices and deterministic local simulation."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib, hmac


@dataclass(frozen=True)
class Reading:
    device_id: int
    vehicle_id: int
    value: float
    timestamp: datetime
    nonce: str
    signature: str


class DeviceAdapter:
    def read(self) -> Reading:
        raise NotImplementedError


class SimulatorAdapter(DeviceAdapter):
    def __init__(self, device_id, vehicle_id, secret, value=0.0):
        self.device_id, self.vehicle_id, self.secret, self.value = device_id, vehicle_id, secret, value

    def read(self):
        timestamp = datetime.now(timezone.utc)
        nonce = hashlib.sha256(timestamp.isoformat().encode()).hexdigest()[:16]
        canonical = f"{self.device_id}.{self.vehicle_id}.{nonce}.{timestamp.isoformat()}.{self.value}"
        sig = hmac.new(self.secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        return Reading(self.device_id, self.vehicle_id, self.value, timestamp, nonce, sig)
