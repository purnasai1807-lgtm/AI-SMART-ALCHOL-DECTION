from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class OrganizationIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class VehicleIn(BaseModel):
    registration: str = Field(min_length=2, max_length=32)
    organization_id: int


class DriverIn(BaseModel):
    name: str
    license_number: str
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
