from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, field_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class APIModel(BaseModel):
    model_config = {"protected_namespaces": ()}


class SensorRequest(APIModel):
    sensors: dict[str, list[FiniteFloat]] = Field(min_length=1)

    @field_validator("sensors")
    @classmethod
    def validate_sensor_names_and_values(cls, value: dict[str, list[float]]) -> dict[str, list[float]]:
        if any(not name.strip() for name in value):
            raise ValueError("sensor names must not be blank")
        if any(not values for values in value.values()):
            raise ValueError("sensor readings must not be empty")
        return value


class FeaturesResponse(APIModel):
    model_version: str
    features: dict[str, float]


class AnomalyResponse(APIModel):
    model_version: str
    score: float = Field(ge=0, le=1)
    anomalous: bool


class PredictionResponse(AnomalyResponse):
    label: str
    safety_decision: str = "DEFERRED"
    safety_override: bool = False
