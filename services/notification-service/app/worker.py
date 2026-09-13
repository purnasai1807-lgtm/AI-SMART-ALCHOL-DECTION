"""Notification outbox worker."""

import json
import os

from .outbox import Outbox
from .providers import (
    EmailProvider,
    InAppProvider,
    Notification,
    NotificationChannel,
    PushProvider,
    SmsProvider,
)


def process_batch(outbox: Outbox, limit: int = 100) -> tuple[int, int]:
    providers = {
        NotificationChannel.IN_APP: InAppProvider(),
        NotificationChannel.EMAIL: EmailProvider(),
        NotificationChannel.SMS: SmsProvider(),
        NotificationChannel.PUSH: PushProvider(),
    }
    max_attempts = int(os.getenv("NOTIFICATION_MAX_ATTEMPTS", "5"))
    sent = failed = 0
    for message in outbox.claim_pending(limit):
        try:
            channel = NotificationChannel(message.channel)
            provider_id = providers[channel].send(Notification(
                channel=channel,
                recipient=message.recipient,
                body=message.body,
                subject=message.subject,
                metadata=json.loads(message.metadata_json),
            ))
            outbox.mark_sent(message.id, provider_id)
            sent += 1
        except Exception as exc:
            outbox.mark_failed(message.id, str(exc), retry=message.attempts < max_attempts)
            failed += 1
    return sent, failed


if __name__ == "__main__":
    process_batch(Outbox(os.getenv("NOTIFICATION_DATABASE_URL", "sqlite:///./notification.db")))
