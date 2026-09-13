"""CLI device simulator for the signed sensor contract.

This generates a payload only. It never claims to unlock or control a vehicle.
"""
import argparse
import hashlib
import hmac
import json
from datetime import datetime, timezone
from secrets import token_urlsafe


def payload(device_id: int, vehicle_id: int, secret: str, reading: float) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    nonce = token_urlsafe(18)
    canonical = f"{device_id}.{vehicle_id}.{nonce}.{timestamp}.{reading}"
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return {
        "device_id": device_id,
        "vehicle_id": vehicle_id,
        "reading": reading,
        "timestamp": timestamp,
        "nonce": nonce,
        "signature": signature,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a signed safety reading payload")
    parser.add_argument("--device-id", type=int, required=True)
    parser.add_argument("--vehicle-id", type=int, required=True)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--reading", type=float, required=True)
    args = parser.parse_args()
    print(json.dumps(payload(args.device_id, args.vehicle_id, args.secret, args.reading)))
