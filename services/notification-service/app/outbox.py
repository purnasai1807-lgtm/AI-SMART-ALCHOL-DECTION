"""Durable SQLAlchemy-backed notification outbox."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class OutboxMessage(Base):
    __tablename__ = "notification_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(998))
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Outbox:
    def __init__(self, database_url: str = "sqlite:///./notification.db") -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def enqueue(
        self,
        *,
        channel: str,
        recipient: str,
        body: str,
        subject: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OutboxMessage:
        message = OutboxMessage(
            id=str(uuid.uuid4()),
            channel=channel,
            recipient=recipient,
            body=body,
            subject=subject,
            metadata_json=json.dumps(metadata or {}, separators=(",", ":")),
            status="pending",
            attempts=0,
            created_at=datetime.now(timezone.utc),
        )
        with self.sessions.begin() as session:
            session.add(message)
        return message

    def get(self, message_id: str) -> OutboxMessage | None:
        with self.sessions() as session:
            return session.scalar(select(OutboxMessage).where(OutboxMessage.id == message_id))

    def pending(self, limit: int = 100) -> list[OutboxMessage]:
        with self.sessions() as session:
            return list(
                session.scalars(
                    select(OutboxMessage)
                    .where(OutboxMessage.status == "pending")
                    .order_by(OutboxMessage.created_at)
                    .limit(limit)
                )
            )
