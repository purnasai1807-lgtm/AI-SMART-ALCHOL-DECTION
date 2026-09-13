from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)


class LoginIn(BaseModel):
    email: EmailStr
    password: str

class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class OrganizationIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class VehicleIn(BaseModel):
    registration: str = Field(min_length=2, max_length=32)
    organization_id: int


class DriverIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    license_number: str = Field(min_length=4, max_length=80)
    organization_id: int


class DeviceIn(BaseModel):
    serial: str
    vehicle_id: int
    secret: str = Field(min_length=16)


class SensorReading(BaseModel):
    device_id: int
    vehicle_id: int
    reading: float = Field(ge=0, le=10)
    timestamp: datetime
    nonce: str = Field(min_length=8, max_length=128)
    signature: str = Field(min_length=16)


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vehicle_id: int
    decision: str
    reason: str
    reading: float | None
    created_at: datetime

class AssignmentIn(BaseModel):
    driver_id: int
    vehicle_id: int

class HeartbeatIn(BaseModel):
    status: str = Field(default="online", pattern="^(online|warning|error|offline)$")

class SensorTestIn(BaseModel):
    vehicle_id: int
    device_id: int | None = None
    samples: list[float] = Field(min_length=3, max_length=20)

class GPSIn(BaseModel):
    vehicle_id: int
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    recorded_at: datetime | None = None

class NotificationIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=1, max_length=2000)
    user_id: int | None = None

class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
