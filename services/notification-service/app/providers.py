"""Provider contracts and safe development adapters.

Third-party delivery is opt-in. No provider silently reports success without
an explicit configured endpoint or credential.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
import os
import uuid


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


@dataclass(frozen=True)
class Notification:
    channel: NotificationChannel
    recipient: str
    body: str
    subject: str | None = None
    metadata: dict[str, Any] | None = None


class NotificationProvider(ABC):
    """Contract for an adapter that can submit one notification."""

    channel: NotificationChannel

    @abstractmethod
    def send(self, notification: Notification) -> str:
        """Submit a notification and return a provider-assigned message ID."""
        raise NotImplementedError


class InAppProvider(NotificationProvider):
    channel = NotificationChannel.IN_APP

    def send(self, notification: Notification) -> str:
        return f"in-app-{uuid.uuid4()}"


class EmailProvider(NotificationProvider):
    channel = NotificationChannel.EMAIL

    def send(self, notification: Notification) -> str:
        if not os.getenv("EMAIL_PROVIDER_URL"):
            raise RuntimeError("EMAIL_PROVIDER_URL is not configured")
        raise RuntimeError("Email provider adapter requires deployment-specific integration")


class SmsProvider(NotificationProvider):
    channel = NotificationChannel.SMS

    def send(self, notification: Notification) -> str:
        if not os.getenv("SMS_PROVIDER_URL"):
            raise RuntimeError("SMS_PROVIDER_URL is not configured")
        raise RuntimeError("SMS provider adapter requires deployment-specific integration")


class PushProvider(NotificationProvider):
    channel = NotificationChannel.PUSH

    def send(self, notification: Notification) -> str:
        if not os.getenv("PUSH_PROVIDER_URL"):
            raise RuntimeError("PUSH_PROVIDER_URL is not configured")
        raise RuntimeError("Push provider adapter requires deployment-specific integration")
