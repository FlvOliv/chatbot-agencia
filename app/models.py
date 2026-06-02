"""Models ORM — leads e conversations.

Schema espelha as tabelas definidas no CLAUDE.md.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
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


class Cliente(Base):
    """Pessoa por trás de um número de WhatsApp.

    Atualizada na primeira mensagem (com `profile_name` vindo da Meta) e
    refinada quando a Malu identifica o nome preferido no briefing.
    """

    __tablename__ = "clientes"

    phone: Mapped[str] = mapped_column(Text, primary_key=True)
    profile_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def display_name(self) -> str | None:
        """Nome preferido (name) com fallback pro profile_name."""
        return self.name or self.profile_name

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cliente phone={self.phone!r} name={self.display_name!r}>"


class Reserva(Base):
    """Viagem já fechada com a Lu. Linkada ao cliente pelo phone.

    A Malu consulta status='ativa' na primeira mensagem do cliente pra
    decidir se oferece o atalho de transferência direta pra Lu.
    """

    __tablename__ = "reservas"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ativa','encerrada','cancelada')",
            name="ck_reservas_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    phone: Mapped[str] = mapped_column(
        Text,
        ForeignKey("clientes.phone", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    codigo_reserva: Mapped[str | None] = mapped_column(Text, nullable=True)
    destino: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_viagem: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="ativa"
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        return f"<Reserva phone={self.phone!r} destino={self.destino!r} status={self.status!r}>"


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
