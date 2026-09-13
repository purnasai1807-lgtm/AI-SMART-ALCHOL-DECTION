"""Durable SQLAlchemy-backed notification outbox."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select, inspect, text
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
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_id: Mapped[str | None] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Outbox:
    def __init__(self, database_url: str = "sqlite:///./notification.db") -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self._upgrade_schema()

    def _upgrade_schema(self) -> None:
        """Add worker columns to databases created by older service versions."""
        columns = {column["name"] for column in inspect(self.engine).get_columns("notification_outbox")}
        additions = {
            "last_error": "TEXT",
            "provider_id": "VARCHAR(255)",
            "sent_at": "DATETIME",
        }
        with self.engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in columns:
                    connection.execute(text(
                        f"ALTER TABLE notification_outbox ADD COLUMN {name} {sql_type}"
                    ))

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

    def claim_pending(self, limit: int = 100) -> list[OutboxMessage]:
        with self.sessions.begin() as session:
            rows = list(session.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.status == "pending")
                .order_by(OutboxMessage.created_at)
                .limit(limit)
            ))
            for row in rows:
                row.status = "processing"
                row.attempts += 1
            return rows

    def mark_sent(self, message_id: str, provider_id: str) -> None:
        with self.sessions.begin() as session:
            row = session.get(OutboxMessage, message_id)
            if row:
                row.status = "sent"
                row.provider_id = provider_id
                row.sent_at = datetime.now(timezone.utc)
                row.last_error = None

    def mark_failed(self, message_id: str, error: str, retry: bool = True) -> None:
        with self.sessions.begin() as session:
            row = session.get(OutboxMessage, message_id)
            if row:
                row.status = "pending" if retry else "failed"
                row.last_error = error[:2000]
