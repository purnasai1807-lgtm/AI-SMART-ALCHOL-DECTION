from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .providers import NotificationChannel


class NotificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: NotificationChannel
    recipient: str = Field(min_length=1, max_length=320)
    body: str = Field(min_length=1, max_length=10000)
    subject: str | None = Field(default=None, max_length=998)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, value: str, info):
        channel = info.data.get("channel")
        if channel == NotificationChannel.EMAIL:
            import re
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
                raise ValueError("recipient must be a valid email address")
        elif channel == NotificationChannel.SMS:
            if not value.startswith("+") or not value[1:].isdigit() or not 8 <= len(value[1:]) <= 15:
                raise ValueError("SMS recipient must be an E.164 phone number")
        return value

    @field_validator("subject")
    @classmethod
    def require_subject_for_email(cls, value: str | None, info):
        if info.data.get("channel") == NotificationChannel.EMAIL and not value:
            raise ValueError("subject is required for email notifications")
        return value


class EnqueueResponse(BaseModel):
    id: str
    status: str
    channel: NotificationChannel
