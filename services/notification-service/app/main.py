import os

from fastapi import FastAPI, status

from .outbox import Outbox
from .schemas import EnqueueResponse, NotificationRequest

outbox = Outbox(os.getenv("NOTIFICATION_DATABASE_URL", "sqlite:///./notification.db"))
app = FastAPI(
    title="Notification Service",
    version="1.0.0",
    description="Durable notification enqueueing; delivery is performed by configured workers.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "notification-service"}


@app.post("/notifications", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_notification(request: NotificationRequest) -> EnqueueResponse:
    message = outbox.enqueue(
        channel=request.channel.value,
        recipient=request.recipient,
        body=request.body,
        subject=request.subject,
        metadata=request.metadata,
    )
    return EnqueueResponse(id=message.id, status="queued", channel=request.channel)
