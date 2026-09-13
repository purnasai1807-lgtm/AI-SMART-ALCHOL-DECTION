"""Provider contracts.

Implementations are deliberately kept outside this service. Enqueuing a message
does not imply that a third-party provider accepted or delivered it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


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


class EmailProvider(NotificationProvider):
    channel = NotificationChannel.EMAIL


class SmsProvider(NotificationProvider):
    channel = NotificationChannel.SMS


class PushProvider(NotificationProvider):
    channel = NotificationChannel.PUSH
