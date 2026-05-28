"""Models ORM — leads e conversations.

Schema espelha as tabelas definidas no CLAUDE.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Lead(Base):
    """Lead capturado pela Malu — uma linha por número de WhatsApp."""

    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "lead_temp IN ('frio','morno','quente','urgente')",
            name="ck_leads_temp",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    phone: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)
    travel_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_temp: Mapped[str | None] = mapped_column(String(16), nullable=True)
    briefing_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Lead phone={self.phone!r} temp={self.lead_temp!r}>"


class Conversation(Base):
    """Log de cada mensagem trocada — auditoria e analytics."""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user','assistant')",
            name="ck_conversations_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    phone: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Conversation phone={self.phone!r} role={self.role!r}>"
